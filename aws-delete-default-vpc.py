#!/usr/bin/env python3

import argparse
import logging
import sys
import boto3
import json

args = None
profile = None
session = None
client_sts = None
client_ec2 = None
regions_include_parsed = []
regions_exclude_parsed = []
regions_chosen = []

# handle input
description = """AWS Delete Default VPC
Deletes the default VPC from the selected regions
Requires valid AWS credentials - either provide a profile name or leave blank to leverage the environment
You must provide EXACTLY one of --all, --include, or --exclude"""
parser = argparse.ArgumentParser(description=description,formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument("-d", "--debug", help = "Print debugging statements", action = "store_true")
parser.add_argument("-p", "--profile", help = "Leverage a pre-configured AWS profile")
parser.add_argument("-l", "--list", help = "List default VPCs and the number of network interfaces and exit", action = "store_true")
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("-a", "--all", help = "Remove default VPCs from all regions in account", action = "store_true")
group.add_argument("-i", "--include", help = "Remove default VPCs from ONLY the proviled region (or comma separated list of regions)")
group.add_argument("-e", "--exclude", help = "Remove default VPCs from ALL regions EXCEPT the provided region (or comma separated list of regions)")
args = parser.parse_args()

# set up logging
logger = logging.getLogger("aws-delete-default-vpcs")
handler = logging.StreamHandler(sys.stdout)
if args.debug:
  formatter = logging.Formatter("%(asctime)s - %(levelname)s: %(message)s")
  handler.setFormatter(formatter)
  logger.addHandler(handler)
  logger.setLevel(logging.DEBUG)
  logger.debug("Debugging verbosity enabled")
else:
  #formatter = logging.Formatter("%(levelname)s: %(message)s")
  #handler.setFormatter(formatter)
  logger.addHandler(handler)
  logger.setLevel(logging.INFO)

if args.list:
  logger.info("List only mode - enumerate default VPCs and number of network interfaces, then exit")

profile = args.profile
if profile is not None:
  logger.debug("Provided profile is " + profile)
else:
  logger.debug("Profile not provided")

if args.include is not None:
  regions_include_parsed = args.include.split(",")
  logger.debug("regions_include_parsed is " + str(regions_include_parsed))

if args.exclude is not None:
  regions_exclude_parsed = args.exclude.split(",")
  logger.debug("regions_exclude_parsed is " + str(regions_exclude_parsed))

# try to use profile (or none) to create session
try:
  if profile is not None:
    logger.info("Attempting to connect as profile: " + profile)
  session = boto3.Session(profile_name=profile)
except:
  logger.error("Invalid profile")
  logger.debug("Note that connection errors could be due to IAM permissions or SCP restrictions")
  exit()

# try to get account number and user context
try:
  client_sts = session.client("sts")
  caller_identity = client_sts.get_caller_identity()
  account_id = caller_identity.get("Account")
  user_id = caller_identity.get("UserId")
  logger.debug("Successfully enumerated session information")
except:
  logger.error("Unable to enumerate session")
  logger.debug("Note that errors enumerating resources could be due to IAM permissions or SCP restrictions")
  exit()

# verify this is the correct account and user!
confirm = input("Enumerate default VPCs as " + user_id + " for account " + account_id + "? [y/N] ")
if confirm.lower() not in ["y","yes"]:
  logger.warning("You must type 'yes' to proceed. Exiting...")
  exit()

# build client
try:
  client_ec2 = session.client("ec2")
  logger.debug("Successfully built client")
except:
  logger.error("Unable to connect clients to session")
  exit()

# get list of regions from account
try:
  regions_described_raw = client_ec2.describe_regions()
  logger.debug("Successfully described regions")
  regions_enabled_raw = regions_described_raw['Regions']
  for region_raw in regions_enabled_raw:
    region_name = region_raw['RegionName']
    logger.debug("Found region " + region_name)
    if args.all == True:
      # enumerate all regions, so include this
      regions_chosen.append(region_name)
      logger.debug("Successfully added region to enumerate because all specified")
    if args.include is not None and region_name in regions_include_parsed:
      # enumerate only specified regions, so only included if specified
      regions_chosen.append(region_name)
      logger.debug("Successfully added region to enumerate because listed in included regions")
    if args.exclude is not None and region_name not in regions_exclude_parsed:
      # enumerate all regions besides the specified ones, so don't include if specified
      regions_chosen.append(region_name)
      logger.debug("Successfully added region to enumerate because not in excluded regions")

  logger.info("Enumerating default VPCs for the following regions:" + str(regions_chosen))
except:
  logger.error("Unable to describe regions in the account")
  logger.debug("Note that errors enumerating resources could be due to IAM permissions or SCP restrictions")
  exit()

# enumerate default VPCs in regions and request deletion
for region in regions_chosen:
  default_vpc_id = ""
  logger.debug("Working specifically with region " + region)
  try:
    logger.debug("Creating new Boto3 EC2 client for region " + region)
    client_ec2 = session.client("ec2", region_name=region)
    logger.debug("Requesting default VPCs from region " + region)
    default_vpc_list = client_ec2.describe_vpcs(Filters=[{"Name":"isDefault","Values":["true"]}])["Vpcs"]
    if len(default_vpc_list) == 1:
      logger.debug("Attempting to parse the default VPC for region " + region)
      default_vpc = default_vpc_list[0]
      default_vpc_id = default_vpc["VpcId"]
      logger.debug("Found default VPC in region " + region + ": " + default_vpc_id + " - " + default_vpc["CidrBlock"])
    else:
      logger.info("No default VPC found in region " + region)
      # skip to next region
      continue
  except:
    logger.error("Unable to enumerate default VPCs for region " + region)
    logger.debug("Note that errors enumerating resources could be due to IAM permissions or SCP restrictions")
    # don't exit the program - we could be blocked by an SCP, so still try other regions
    continue

  # enumerate number of network intefaces in default VPC and either exit (if "list" flag enabled) or skip if not empty
  try:
    logger.debug("Attempting to enumerate network interfaces in default VPC in region " + region + " with ID " + default_vpc_id)
    interfaces = client_ec2.describe_network_interfaces(Filters=[{"Name":"vpc-id","Values":[default_vpc_id]}])["NetworkInterfaces"]
    if args.list:
      # "list" flag provided, so print default VPC information and skip deletion
      logger.info("Found default VPC in region " + region + " with ID " + default_vpc_id + " and " + str(len(interfaces)) + " network interfaces")
      continue
    if len(interfaces) > 0:
      logger.warning("Default VPC in region " + region + " with ID " + default_vpc_id + " is not empty with " + str(len(interfaces)) + " network interfaces")
      continue
    logger.debug("No network interfaces found for default VPC in region " + region + " with ID " + default_vpc_id)
  except:
    logger.error("Problem enumerating network interfaces for default VPC in region " + region + " with ID " + default_vpc_id)
    logger.debug("Note that errors enumerating resources could be due to IAM permissions or SCP restrictions")
    # don't exit the program - we could be blocked by an SCP, so still try other regions
    continue

  # delete empty default VPCs
  try:
    confirm = input("Would you like to delete empty default VPC in region " + region + " with ID " + default_vpc_id + "? [y/N] ")
    if confirm.lower() not in ["y","yes"]:
      logger.warning("Skipping deletion of VPC at user request")
      continue
    else:
      logger.info("Deleting default VPC in region " + region + " with ID " + default_vpc_id + "... - NOT YET")
      # TODO: Delete subnets, etc. and then vpcs
  except:
    logger.error("Unable to delete default VPC in region " + region + " with ID " + default_vpc_id)
    continue
