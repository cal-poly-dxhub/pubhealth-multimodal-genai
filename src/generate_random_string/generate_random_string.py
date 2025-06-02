import logging
import os
import random
import string

import boto3
import botocore
import cfnresponse

client = boto3.client("ssm")

LOG_LEVEL = os.getenv("LOG_LEVEL")


def lambda_handler(event, context):
    global log_level
    log_level = str(LOG_LEVEL).upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        log_level = "ERROR"
    logging.getLogger().setLevel(log_level)

    logging.info(f"Event: {event}")

    request_type = event["RequestType"]

    if request_type == "Delete":
        security_profile_name = event["ResourceProperties"][
            "SecurityProfileName"
        ]
        try:
            response = client.delete_parameter(
                Name=f"amazon-connect-temp-{security_profile_name}-password"
            )

            cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
            return
        except botocore.exceptions.ClientError as err:
            if err.response["Error"]["Code"] == "ParameterNotFound":
                cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
                return
            else:
                logging.error(err)
                cfnresponse.send(
                    event,
                    context,
                    cfnresponse.FAILED,
                    {"message": f"ERROR: {err}"},
                )
                return
        except Exception as e:
            logging.error(e)
            cfnresponse.send(
                event, context, cfnresponse.FAILED, {"message": f"ERROR: {e}"}
            )
            return

    if request_type in {"Create", "Update"}:
        try:
            string_length = event["ResourceProperties"]["StringLength"]
            security_profile_name = event["ResourceProperties"][
                "SecurityProfileName"
            ]

            valid_characters = (
                string.ascii_letters + string.digits + "!@#$%^&*_=-"
            )
            # First 4 specifies a mix of from each combination
            random_string = random.SystemRandom().choice(string.ascii_lowercase)
            random_string += random.SystemRandom().choice(
                string.ascii_uppercase
            )
            random_string += random.SystemRandom().choice(string.digits)
            random_string += random.SystemRandom().choice("!@#$%^&*_=-")

            for i in range(int(string_length) - 4):
                random_string += random.SystemRandom().choice(valid_characters)

            response = client.put_parameter(
                Name=f"amazon-connect-temp-{security_profile_name}-password",
                Description=f"SSM Parameter to store the temporary Amazon Connect {security_profile_name} Password",
                Value=random_string,
                Type="SecureString",
                Overwrite=True,
                Tier="Standard",
            )

            response_data = {"RandomString": random_string}
            cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data)
        except Exception as e:
            logging.error(e)
            cfnresponse.send(
                event, context, cfnresponse.FAILED, {"message": f"ERROR: {e}"}
            )
            return
