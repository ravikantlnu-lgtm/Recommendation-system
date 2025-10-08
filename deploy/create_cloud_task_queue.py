"""Creates a Google Cloud Tasks queue with specified parameters.

This script creates a Cloud Tasks queue with configurable retry and rate limit settings.
The queue is created in the specified Google Cloud project and location.

Examples:
    Run with default values:
        $ python create_cloud_task_queue.py

    Run with custom project ID:
        $ python create_cloud_task_queue.py --project-id="my-project-id"

    Run with all custom values:
        $ python create_cloud_task_queue.py \
            --project-id="my-project-id" \
            --location="us-central1" \
            --queue-name="my-custom-queue"

Returns:
    None. Prints the name of the created queue to stdout.
"""

import argparse

from google.cloud import tasks_v2
from google.protobuf import duration_pb2


def create_task_queue(project_id, location, queue_name):
    client = tasks_v2.CloudTasksClient()

    parent = f"projects/{project_id}/locations/{location}"

    queue = {
        "name": client.queue_path(project_id, location, queue_name),
        "rate_limits": {
            "max_dispatches_per_second": 2,
            "max_concurrent_dispatches": 1000,
        },
        "retry_config": {
            "max_attempts": 100,
            "max_retry_duration": duration_pb2.Duration(seconds=3600),
            "min_backoff": duration_pb2.Duration(
                seconds=0, nanos=int(0.1 * 1_000_000_000)
            ),
            "max_backoff": duration_pb2.Duration(seconds=3600),
            "max_doublings": 16,
        },
    }

    response = client.create_queue(parent=parent, queue=queue)
    print(f"Queue created: {response.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a Cloud Tasks queue with specified parameters"
    )
    parser.add_argument(
        "--project-id",
        default="proj-sales-recommender-dev",
        help="Google Cloud project ID (default: proj-sales-recommender-dev)",
    )
    parser.add_argument(
        "--location", default="us-west1", help="Queue location (default: us-west1)"
    )
    parser.add_argument(
        "--queue-name",
        default="project-queue",
        help="Name of the queue to create (default: project-queue)",
    )

    args = parser.parse_args()

    create_task_queue(args.project_id, args.location, args.queue_name)
