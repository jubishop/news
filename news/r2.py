"""Read all object sizes in the dedicated R2 bucket using S3 Signature V4."""

import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def setting(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing {name} in backup environment")
    return value


def bucket_url():
    repository = setting("RESTIC_REPOSITORY")
    if not repository.startswith("s3:https://"):
        raise ValueError("Backup size monitoring requires an HTTPS R2 repository")
    url = urllib.parse.urlsplit(repository[3:])
    bucket = url.path.strip("/").split("/")[0]
    if (
        not url.hostname
        or not url.hostname.endswith(".r2.cloudflarestorage.com")
        or url.username
        or url.password
        or url.port
        or url.query
        or url.fragment
        or not bucket
    ):
        raise ValueError("Invalid R2 backup repository URL")
    return urllib.parse.urlunsplit(("https", url.hostname, "/" + bucket, "", ""))


def list_bucket(url, access, secret):
    total, count = 0, 0
    token = None
    seen = set()
    parsed = urllib.parse.urlsplit(url)
    while True:
        parameters = {"list-type": "2", "max-keys": "1000"}
        if token:
            parameters["continuation-token"] = token
        query = urllib.parse.urlencode(
            sorted(parameters.items()), quote_via=urllib.parse.quote
        )
        stamp = datetime.datetime.fromtimestamp(
            time.time(), datetime.timezone.utc
        ).strftime("%Y%m%dT%H%M%SZ")
        day = stamp[:8]
        digest = hashlib.sha256(b"").hexdigest()
        headers = {
            "host": parsed.netloc,
            "x-amz-content-sha256": digest,
            "x-amz-date": stamp,
        }
        signed = ";".join(headers)
        canonical = "\n".join(
            (
                "GET",
                parsed.path,
                query,
                "".join(f"{key}:{value}\n" for key, value in headers.items()),
                signed,
                digest,
            )
        )
        scope = f"{day}/auto/s3/aws4_request"
        to_sign = "\n".join(
            (
                "AWS4-HMAC-SHA256",
                stamp,
                scope,
                hashlib.sha256(canonical.encode()).hexdigest(),
            )
        )
        key = ("AWS4" + secret).encode()
        for part in (day, "auto", "s3", "aws4_request"):
            key = hmac.new(key, part.encode(), hashlib.sha256).digest()
        signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
        headers["Authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={access}/{scope}, "
            f"SignedHeaders={signed}, Signature={signature}"
        )
        request = urllib.request.Request(url + "?" + query, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            root = ET.fromstring(response.read())
        if root.tag.split("}")[-1] != "ListBucketResult":
            raise ValueError("Invalid R2 listing response")
        for item in root.findall("{*}Contents"):
            size = int(item.findtext("{*}Size", "-1"))
            if size < 0:
                raise ValueError("Invalid R2 object size")
            total += size
            count += 1
        truncated = root.findtext("{*}IsTruncated")
        if truncated == "false":
            return total, count
        token = root.findtext("{*}NextContinuationToken")
        if truncated != "true" or not token or token in seen:
            raise ValueError("Invalid R2 listing continuation")
        seen.add(token)


def save(path, state):
    descriptor, temporary = tempfile.mkstemp(prefix=".size-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump(state, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)
