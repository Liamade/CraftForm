# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                               CraftForm                                      ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  OPERATIONS LAMBDA  ::  services/s3.py                                       ║
# ║  Little shared helpers for peeking at the per-region world-data buckets.     ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ==========================================================================================
#                                   S3 HELPERS
# ==========================================================================================
# every region has its own "craftform-<region>-<account>" bucket holding the world data.
# we mostly just need to peek at these (e.g. "is it empty before we tear the region down?")
# ------------------------------------------------------------------------------------------
from aws_clients import s3  # shared client -- made once per cold start


# =================================BUCKET HAS OBJECTS====================================
# cheapest possible "is this bucket empty?" check -- ask for just a SINGLE key. if even one
# comes back, there's data in there. we don't list the whole bucket, we just peek :)
def bucket_has_objects(bucket):
    response = s3.list_objects_v2(Bucket=bucket, MaxKeys=1)
    return response.get("KeyCount", 0) > 0
