from functools import lru_cache

import boto3
from botocore.config import Config

from .config import settings


@lru_cache
def client():
    cfg = settings()
    return boto3.client(
        "s3", endpoint_url=cfg.s3_endpoint, region_name=cfg.s3_region,
        aws_access_key_id=cfg.s3_access_key,
        aws_secret_access_key=cfg.s3_secret_key.get_secret_value() if cfg.s3_secret_key else None,
        config=Config(
            connect_timeout=4, read_timeout=15, retries={"max_attempts": 2},
            s3={"addressing_style": "path" if cfg.s3_endpoint else "auto"},
        ),
    )


def put_file(key, file):
    client().upload_fileobj(file, settings().s3_bucket, key, ExtraArgs={"ContentType": "application/octet-stream"})


def get_file(key, path):
    client().download_file(settings().s3_bucket, key, str(path))


def put_evidence(key, data):
    client().put_object(Bucket=settings().s3_bucket, Key=key, Body=data, ContentType="image/jpeg")


def read_evidence(key):
    return client().get_object(Bucket=settings().s3_bucket, Key=key)["Body"]


def delete(key):
    client().delete_object(Bucket=settings().s3_bucket, Key=key)
