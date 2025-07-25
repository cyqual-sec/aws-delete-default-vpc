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
description = """Deletes the default VPC from the selected regions
- Requires valid AWS credentials - either provide a profile name or leave blank to leverage the environment
- You must provide EXACTLY one of --all, --include, or --exclude"""
parser = argparse.ArgumentParser(description=description,formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument("-v", "--verbose", help = "Print verbose statements for debugging", action = "store_true")
parser.add_argument("-p", "--profile", help = "Leverage a pre-configured AWS profile")
parser.add_argument("-l", "--list", help = "Only list default VPCs and their number of network interfaces and exit", action = "store_true")
parser.add_argument("-y", "--yolo", help = "Don't ask for confirmation to delete VPCs and DHCP option sets", action = "store_true")
group_regions = parser.add_argument_group("AWS regions", "Specify the AWS regions to enumerate (e.g., us-east-1)")
group_regions_exclusive = group_regions.add_mutually_exclusive_group(required=True)
group_regions_exclusive.add_argument("-a", "--all", help = "Remove default VPCs from all regions in account", action = "store_true")
group_regions_exclusive.add_argument("-i", "--include", help = "Remove default VPCs from ONLY the provided region (or comma separated list of regions)")
group_regions_exclusive.add_argument("-e", "--exclude", help = "Remove default VPCs from ALL regions EXCEPT the provided region (or comma separated list of regions)")
args = parser.parse_args()

# set up logging
logger = logging.getLogger("aws-delete-default-vpcs")
handler = logging.StreamHandler(sys.stdout)
if args.verbose:
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

if args.list and args.yolo:
  logger.error("How can we only list and also yolo delete?")
  logger.debug("Both args.list and args.yolo shouldn't be set")
  exit()

if args.list:
  logger.info("List only mode - enumerate default VPCs and number of network interfaces, then exit")

if args.yolo:
  logger.info("Auto-accepting deletion of default VPCs and DHCP option sets")

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
except Exception as e:
  logger.error("Invalid or disconnected profile")
  logger.debug("Note that connection errors could be due to expired keys, missing IAM permissions, or SCP restrictions")
  logger.debug(e)
  exit()

# try to get account number and user context
try:
  client_sts = session.client("sts")
  caller_identity = client_sts.get_caller_identity()
  account_id = caller_identity.get("Account")
  user_id = caller_identity.get("UserId")
  logger.debug("Successfully enumerated session information")
except Exception as e:
  logger.error("Unable to enumerate session")
  logger.debug("Note that errors enumerating resources could be due to missing IAM permissions or SCP restrictions")
  logger.debug(e)
  exit()

# verify this is the correct account and user!
confirm = input("Enumerate default VPCs as " + user_id + " for account " + account_id + "? [y/N] ")
if confirm.lower() not in ["y","yes"]:
  logger.warning("You must type 'yes' to proceed. Exiting...")
  exit()

# build client to enumerate regions
try:
  client_ec2 = session.client("ec2")
  logger.debug("Successfully built client")
except Exception as e:
  logger.error("Unable to connect clients to session")
  logger.debug(e)
  exit()

# get list of regions from account
try:
  regions_described_raw = client_ec2.describe_regions()
  logger.debug("Successfully described regions")
  regions_enabled_raw = regions_described_raw['Regions']
  regions_enabled = []

  logger.debug("Parsing raw region list and extracting region names")
  for region_raw in regions_enabled_raw:
    logger.debug("Found region " + region_raw['RegionName'])
    regions_enabled.append(region_raw['RegionName'])

  # check if any included or excluded regions were provided and available (to catch misspellings)
  if args.include is not None:
    logger.debug("Validating that provided regions to include are enabled")
    regions_include_missing = list(set(regions_include_parsed)-set(regions_enabled))
    if len(regions_include_missing) > 0:
      logger.error("The following provided regions to include are not available  " + str(regions_include_missing))
      exit()

  if args.exclude is not None:
    logger.debug("Validating that provided regions to exclude are enabled")
    regions_exclude_missing = list(set(regions_exclude_parsed)-set(regions_enabled))
    if len(regions_exclude_missing) > 0:
      logger.error("The following provided regions to exclude are not available  " + str(regions_exclude_missing))
      exit()

  # create list of regions to work on by applying user input to enabled regions
  for region_name in regions_enabled:
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
except Exception as e:
  logger.error("Unable to describe regions in the account")
  logger.debug("Note that errors enumerating resources could be due to IAM permissions or SCP restrictions")
  logger.debug(e)
  exit()

# enumerate default VPCs in regions and request deletion
for region in regions_chosen:
  default_vpc = ""
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
      default_dhcp_options_id = default_vpc["DhcpOptionsId"]
      logger.debug("Found default VPC in region " + region + ": " + default_vpc_id + " - " + default_vpc["CidrBlock"])
    else:
      logger.info("No default VPC found in region " + region)
      # skip to next region
      continue
  except Exception as e:
    logger.error("Unable to enumerate default VPCs for region " + region)
    logger.debug("Note that errors enumerating resources could be due to IAM permissions or SCP restrictions")
    logger.debug(e)
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
  except Exception as e:
    logger.error("Problem enumerating network interfaces for default VPC in region " + region + " with ID " + default_vpc_id)
    logger.debug("Note that errors enumerating resources could be due to IAM permissions or SCP restrictions")
    logger.debug(e)
    # don't exit the program - we could be blocked by an SCP, so still try other regions
    continue

  # delete empty default VPCs
  try:
    if not args.yolo:
      confirm = input("Would you like to delete empty default VPC in region " + region + " with ID " + default_vpc_id + "? [y/N] ")
    else:
      confirm = "yes" # yolo
    if confirm.lower() not in ["y","yes"]:
      logger.warning("Skipping deletion of VPC at user request")
      continue
    else:
      logger.info("Deleting default VPC in region " + region + " with ID " + default_vpc_id + "...")
      logger.debug("Enumerating internet gatways for default VPC in region " + region + " with ID " + default_vpc_id)
      igw_list = client_ec2.describe_internet_gateways(Filters=[{"Name": "attachment.vpc-id", "Values": [default_vpc_id]}])["InternetGateways"]
      if len(igw_list) == 0:
        logger.error("Did not detect an internet gateway for default VPC in region " + region + " with ID " + default_vpc_id)
        continue
      else:
        igw_id = igw_list[0]["InternetGatewayId"]
        logger.debug("Found internet gateway with ID " + igw_id + " for default VPC in region " + region + " with ID " + default_vpc_id)
        logger.debug("Detaching internet gateway with ID " + igw_id + " for default VPC in region " + region + " with ID " + default_vpc_id)
        client_ec2.detach_internet_gateway(InternetGatewayId=igw_id, VpcId=default_vpc_id)
        logger.debug("Deleting internet gateway with ID " + igw_id + " for default VPC in region " + region + " with ID " + default_vpc_id)
        client_ec2.delete_internet_gateway(InternetGatewayId=igw_id)

      logger.debug("Enumerating subnets for default VPC in region " + region + " with ID " + default_vpc_id)
      subnet_list = client_ec2.describe_subnets(Filters=[{"Name":"vpc-id", "Values":[default_vpc_id]}])["Subnets"]
      if len(subnet_list) == 0:
        logger.error("Did not detect subnets for default VPC in region " + region + " with ID " + default_vpc_id)
        continue
      else:
        logger.debug("Found " + str(len(subnet_list)) + " subnets for default VPC in region " + region + " with ID " + default_vpc_id)
        for subnet in subnet_list:
          subnet_id =  subnet["SubnetId"]
          logger.debug("Deleting subnet with ID " + subnet_id + " for default VPC in region " + region + " with ID " + default_vpc_id)
          client_ec2.delete_subnet(SubnetId=subnet_id)

      logger.debug("Deleting default VPC in region " + region + " with ID " + default_vpc_id)
      client_ec2.delete_vpc(VpcId=default_vpc_id)
  except Exception as e:
    logger.error("Unable to delete default VPC in region " + region + " with ID " + default_vpc_id)
    logger.debug(e)
    continue

  # remove default DHCP option set
  try:
    logger.debug("Checking for default dhcp options set usage in region " + region + " with ID " + default_dhcp_options_id)
    dhcp_options_vpc_list = client_ec2.describe_vpcs(Filters=[{"Name":"dhcp-options-id","Values":[default_dhcp_options_id]}])["Vpcs"]
    if len(dhcp_options_vpc_list) == 0:
      if not args.yolo:
        confirm = input("Would you like to delete the unused default DHCP option set in region " + region + " with ID " + default_dhcp_options_id + "? [y/N] ")
      else:
        confirm = "yes" # yolo
      if confirm.lower() not in ["y","yes"]:
        logger.warning("Skipping deletion of VPC at user request")
      else:
        client_ec2.delete_dhcp_options(DhcpOptionsId=default_dhcp_options_id)
    else:
      logger.warning("DHCP options set with ID " + default_dhcp_options_id + " is used by another VPC and cannot be deleted")
  except Exception as e:
    logger.error("Problem enumerating DHCP option set usage or deleting an unsed one in region " + region)
    logger.debug(e)
    continue
