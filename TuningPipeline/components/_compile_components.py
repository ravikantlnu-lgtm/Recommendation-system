import os
import argparse
import subprocess

def compile_components():
    """
    Compile and run all Python component files in the current directory.

    This function performs the following tasks:
    1. Sets up an argument parser to accept the 'latest_image_name' parameter.
    2. Changes the working directory to 'components'.
    3. Iterates through all Python files in the directory (excluding '_compile_components.py').
    4. Executes each Python file with the provided 'latest_image_name' as a command-line argument.

    The function uses subprocess to run each component file, passing the 'latest_image_name'
    as the '--base_image' parameter. It prints the command being executed and handles any
    errors that occur during execution.

    Args:
        None

    Returns:
        None

    Raises:
        subprocess.CalledProcessError: If any of the component scripts fail to execute.

    Note:
        This function is designed to be run as a script and relies on command-line arguments.
        It expects the '--latest_image_name' argument to be provided when the script is run.
    """
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Run Python files with a base image parameter.")
    parser.add_argument("-i", "--latest_image_name", required=True, help="The name of the latest image to use")
    args = parser.parse_args()

    os.chdir("components")
    # Loop through all files in the directory
    for filename in os.listdir():
        if filename.endswith(".py") and filename != '_compile_components.py':
           
            # Construct the command
            command = f"python {filename} --base_image {args.latest_image_name}"
            
            print(f"Running: {command}")
            
            # Run the command
            try:
                subprocess.run(command, shell=True, check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error running {filename}: {e}")

if __name__ == "__main__":
    compile_components()