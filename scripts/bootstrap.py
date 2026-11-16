from botocore.exceptions import ClientError

from safevision.config import settings
from safevision.db import Camera, sessions
from safevision.storage import client


def main():
    cfg = settings()
    s3 = client()
    try:
        s3.head_bucket(Bucket=cfg.s3_bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("404", "NoSuchBucket", "NotFound"):
            raise
        options = {}
        if cfg.s3_region != "us-east-1":
            options["CreateBucketConfiguration"] = {"LocationConstraint": cfg.s3_region}
        s3.create_bucket(Bucket=cfg.s3_bucket, **options)
    with sessions()() as db:
        if db.get(Camera, "cam-01") is None:
            db.add(Camera(id="cam-01", name="Câmera padrão", location="Entrada de arquivos"))
        db.commit()


if __name__ == "__main__":
    main()
