# aws-delete-default-vpc

A small python script to detect and delete default VPCs in a user-defined set of regions. Supports processing all enabled regions, only a set of specified regions (include), and all but a set of specified regions (exclude).

## Background

AWS automatically creates networking resources for new accounts. Each region includes a default VPC along with the following sub-resources:
- subnet per availabiliy zone in the region
- route table
- network security group
- network access control list (ACL)
- internet gateway
- DHCP options set

Although these resources are free and do not inherently pose a security risk, any new network resources created in the region will be placed in the default VPC unless another VPC is specified. This has the potential to create problems. For example, if critical workloads are built into the default VPC and a new resource is deployed through a console wizard, the new resource could end up in the with access to internal networks of the critical workloads.

More importantly, the AWS console can be frustrating to deal with, and users frequently end up in a different region than they expect. This frequently results in resources being unexpectedly created in unauthorized regions, and these resources can sit for a long time unnoticed, adding unnecessarily to cost and potential attack surface.

## Recommendations

USE AT YOUR OWN RISK!

Ultimately, you are responsible for the operation and security of your AWS resources. However, best practice is to either remove or restrict access to these default VPCs and associated resources to avoid the problems described above. Many AWS configuration scanners, also known as Cloud Security Posture Management (CPSM) software, will flag the existance of default VPCs and the permissive nature of their configurations, and removing them manually for remediation can take time.

Specifically, consider running this script:
1. with -a for new accounts to clear out all default VPCs

       python aws-delete-default-vpc.py -a

2. with -i and provide an unused region to validate that it works

       python aws-delete-default-vpc.py -i sa-east-1

3. with -e and provide your active regions to remove unused default VPCs

       python aws-delete-default-vpc.py -e us-east-1,us-west-2

When networking is required in a region, engineers should intentionally create a new VPC with configurations specific to the project's expected workloads. Although these new VPCs will not automatically be designated as the "default" VPC (a special resource flag), new default VPCs can be created through the AWS CLI: https://docs.aws.amazon.com/vpc/latest/userguide/default-vpc.html

## Usage

    usage: aws-delete-default-vpc.py [-h] [-v] [-p PROFILE] [-l] (-a | -i INCLUDE | -e EXCLUDE)

    Deletes the default VPC from the selected regions
    - Requires valid AWS credentials - either provide a profile name or leave blank to leverage the environment
    - You must provide EXACTLY one of --all, --include, or --exclude

    optional arguments:
      -h, --help            show this help message and exit
      -v, --verbose         Print verbose statements for debugging
      -p PROFILE, --profile PROFILE
                            Leverage a pre-configured AWS profile
      -l, --list            Only list default VPCs and their number of network interfaces and exit

    AWS regions:
      Specify the AWS regions to enumerate (e.g., us-east-1)

      -a, --all             Remove default VPCs from all regions in account
      -i INCLUDE, --include INCLUDE
                            Remove default VPCs from ONLY the provided region (or comma separated list of regions)
      -e EXCLUDE, --exclude EXCLUDE
                            Remove default VPCs from ALL regions EXCEPT the provided region (or comma separated list of regions)