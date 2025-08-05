import json
import logging
import os

import boto3
import cfnresponse
import pg8000
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_secret(secret_name):
    client = boto3.client("secretsmanager")
    try:
        response = client.get_secret_value(SecretId=secret_name)
        return json.loads(response["SecretString"])
    except ClientError as e:
        logger.error(f"Error retrieving secret: {e}")
        raise e


def handler(event, context):
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        # Only process create/update events
        if event["RequestType"] in ["Create", "Update"]:
            secret_arn = os.environ["DB_SECRET_ARN"]
            host = os.environ["DB_HOST"]
            db_name = os.environ["DB_NAME"]

            # Get database credentials
            secret = get_secret(secret_arn)
            username = secret["username"]
            password = secret["password"]

            # Connect to database using pg8000
            conn = pg8000.connect(
                host=host,
                port=5432,
                database=db_name,
                user=username,
                password=password,
            )
            conn.autocommit = True

            # Setup db for Bedrock access
            with conn.cursor() as cur:
                logger.info("Enabling pgvector extension")
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

                logger.info("Creating schema")
                cur.execute("CREATE SCHEMA IF NOT EXISTS bedrock_integration;")

                logger.info("Creating bedrock user role")
                cur.execute(
                    "CREATE ROLE bedrock_user WITH PASSWORD 'password' LOGIN;"
                )

                logger.info("Granting permissions")
                cur.execute(
                    "GRANT ALL ON SCHEMA bedrock_integration to bedrock_user;"
                )

                logger.info("Creating table")
                cur.execute("""
                CREATE TABLE IF NOT EXISTS bedrock_integration.bedrock_kb (
                    id uuid PRIMARY KEY,
                    embedding vector(1024),
                    chunks text,
                    metadata json,
                    custom_metadata jsonb
                );""")

                logger.info("Creating indexes")
                cur.execute(
                    """CREATE INDEX ON bedrock_integration.bedrock_kb USING hnsw (embedding vector_cosine_ops);"""
                )

                cur.execute(
                    """CREATE INDEX ON bedrock_integration.bedrock_kb USING gin (to_tsvector('simple', chunks));"""
                )

            conn.close()
            logger.info("Database setup completed successfully")

        cfnresponse.send(
            event,
            context,
            cfnresponse.SUCCESS,
            {"Message": "Configuration complete"},
        )
    except Exception as e:
        logger.error(f"Error setting up database: {e}")
        cfnresponse.send(event, context, cfnresponse.FAILED, {"Error": str(e)})
