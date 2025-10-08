"""
Deploys a Google Cloud Function with specified parameters.
This script copies the main cloud function file to a new file named `main.py` in the specified source directory 
and then deploys the cloud function using the Google Cloud SDK (`gcloud` command). 
The deployment includes configurable parameters such as function name, entry point, runtime, region, memory, CPU, concurrency, timeout, and service account.
Examples:
    Run with required parameters:
        $ python deploy_cloud_function.py --function-name="my-function" --source-dir="/path/to/source" --entry-point="main" --main-cloud-function-file="main_function.py"
    Run with custom runtime and region:
        $ python deploy_cloud_function.py --function-name="my-function" --source-dir="/path/to/source" --entry-point="main" --main-cloud-function-file="main_function.py" --runtime="python39" --region="europe-west1"
    Run with all custom values:
        $ python deploy_cloud_function.py \
            --function-name="my-function" \
            --source-dir="/path/to/source" \
            --entry-point="main" \
            --main-cloud-function-file="main_function.py" \
            --runtime="python39" \
            --region="europe-west1" \
            --memory="512MB" \
            --cpu="2" \
            --concurrency=1 \
            --timeout=600 \
            --service-account="my-service-account@my-project.iam.gserviceaccount.com" \
            --secrets="ENV_VAR_NAME=SECRET_NAME:VERSION"
Returns:
    None. Prints the status of file copying and function deployment to stdout.
"""
import argparse
import shutil
import subprocess
from typing import Optional


def create_main_file(source_dir: str, main_cloud_function_file: str) -> None:
    source_file = f"{source_dir}/{main_cloud_function_file}"
    destination_file = f"{source_dir}/main.py"

    try:
        shutil.copy(source_file, destination_file)
        print("File copied successfully.")
    except FileNotFoundError:
        print("Error: The source file does not exist.")
    except PermissionError:
        print("Error: Permission denied. Please check your file permissions.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def deploy_cloud_function(function_name: str, 
                        source_dir: str, 
                        entry_point: str, 
                        runtime: str, 
                        region: str, 
                        memory: str, 
                        cpu: str,
                        env: str, 
                        concurrency: Optional[int], 
                        timeout: Optional[int], 
                        service_account: Optional[str], 
                        max_instances: Optional[int],
                        secrets : Optional [str]) -> None:
    command = [
        "gcloud", "functions", "deploy", function_name,
        "--source", source_dir,
        "--entry-point", entry_point,
        "--runtime", runtime,
        "--trigger-http",
        "--no-allow-unauthenticated",
        "--region", region,
        "--memory", memory,
        "--cpu", cpu,
        "--set-env-vars", env
        
    ]
    
    if service_account:
        command.extend(["--service-account", service_account])
    
    if concurrency is not None:
        command.extend(["--concurrency", str(concurrency)])
    
    if max_instances is not None:
        command.extend(["--max-instances", str(max_instances)])

    if timeout is not None:
        command.extend(["--timeout", f"{timeout}s"])

    if secrets is not None:
        command.extend(["--set-secrets", f"{secrets}"])

    try:
        result = subprocess.run(command, check=True, text=True, capture_output=True)
        print(f"Function '{function_name}' deployed successfully:\n{result.stdout}")
    except subprocess.CalledProcessError as e:
        print(f"Error deploying function:\n{e.stderr}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy a Google Cloud Function with specified parameters")
    parser.add_argument("--function-name", required=True, help="The name of the cloud function to deploy")
    parser.add_argument("--source-dir", required=True, help="The directory containing the source code for the function")
    parser.add_argument("--entry-point", required=True, help="The name of the function to be executed")
    parser.add_argument("--main-cloud-function-file", required=True, help="The main cloud function file to be copied")
    parser.add_argument("--runtime", default="python39", help="The runtime environment for the function (default: python39)")
    parser.add_argument("--region", default="us-west1", help="The region where the function will be deployed (default: us-west1)")
    parser.add_argument("--memory", default="1GiB", help="The amount of memory allocated to the function (default: 256MB)")
    parser.add_argument("--cpu", default="2", help="The number of CPU cores allocated to the function (default: 1)")
    parser.add_argument("--concurrency", default= 1, type=int, help="The maximum number of concurrent executions (optional)")
    parser.add_argument("--timeout", default= 3600, type=int, help="The function execution timeout in seconds (optional)")
    parser.add_argument("--max-instances", type=int, help="The maximum number of instances to be created (optional)")
    parser.add_argument("--service-account", help="The service account to be used by the function (optional)")
    parser.add_argument("--secrets", help="The secrets to be used by the function (optional)")
    parser.add_argument("--env",required=True)
    args = parser.parse_args()

    create_main_file(args.source_dir, args.main_cloud_function_file)
    
    deploy_cloud_function(
        function_name=args.function_name, 
        source_dir=args.source_dir, 
        entry_point=args.entry_point, 
        runtime=args.runtime, 
        region=args.region,
        memory=args.memory, 
        cpu=args.cpu, 
        env=args.env, 
        concurrency=args.concurrency, 
        timeout=args.timeout, 
        service_account=args.service_account,
        max_instances=args.max_instances,
        secrets=args.secrets
    )
