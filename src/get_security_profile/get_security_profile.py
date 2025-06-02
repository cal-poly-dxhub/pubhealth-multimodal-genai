import logging
import os

import boto3
import cfnresponse

client = boto3.client("connect")

LOG_LEVEL = os.getenv("LOG_LEVEL")
INSTANCE_ID = os.getenv("INSTANCE_ID")


def lambda_handler(event, context):
    global log_level
    log_level = str(LOG_LEVEL).upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        log_level = "ERROR"
    logging.getLogger().setLevel(log_level)

    logging.info(f"Event: {event}")

    request_type = event["RequestType"]

    if request_type == "Delete":
        cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
        return

    if request_type in {"Create", "Update"}:
        try:
            security_profile_name = event["ResourceProperties"][
                "SecurityProfileName"
            ]

            marker = None

            while True:
                paginator = client.get_paginator("list_security_profiles")
                response_iterator = paginator.paginate(
                    InstanceId=INSTANCE_ID,
                    PaginationConfig={"PageSize": 10, "StartingToken": marker},
                )
                for page in response_iterator:
                    security_profiles = page["SecurityProfileSummaryList"]
                    for security_profile in security_profiles:
                        if security_profile["Name"] == security_profile_name:
                            response_data = {
                                "SecurityProfileId": security_profile["Id"],
                                "SecurityProfileArn": security_profile["Arn"],
                            }
                            cfnresponse.send(
                                event,
                                context,
                                cfnresponse.SUCCESS,
                                response_data,
                            )
                            return
                try:
                    marker = response_iterator["Marker"]
                except Exception as e:
                    logging.error(e)
                    cfnresponse.send(
                        event,
                        context,
                        cfnresponse.FAILED,
                        {"message": f"ERROR: {e}"},
                    )
                    break
        except Exception as e:
            logging.error(e)
            cfnresponse.send(
                event, context, cfnresponse.FAILED, {"message": f"ERROR: {e}"}
            )
            return
