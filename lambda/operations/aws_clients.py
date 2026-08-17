# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                               CraftForm                                      ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  OPERATIONS LAMBDA  ::  aws_clients.py                                       ║
# ║  One shared home for the boto3 clients used across the command handlers.     ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ==========================================================================================
#                               SHARED AWS CLIENTS
# ==========================================================================================
# these live at module level on purpose -- lambda builds them ONCE per cold start and reuses
# this way we don't have to rebuild the clients everytime to call them
# ------------------------------------------------------------------------------------------
import boto3

ssm           = boto3.client("ssm")             # parameter store -- config + per-region discovery
secrets       = boto3.client("secretsmanager")  # the craftform secret bundle (discord bot token)
lambda_client = boto3.client("lambda")          # invoking other craftform functions (e.g. /update -> staging)
ec2           = boto3.client("ec2")             # used for describe_regions to list all available AWS regions
s3            = boto3.client("s3")              # peek into per-region world buckets (empty-check before delete)
codebuild     = boto3.client("codebuild")       # kicks off the long builds -- craftform-region + craftform-server
