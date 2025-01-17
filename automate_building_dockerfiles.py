#####################################
#
# Commands to run, 
# 1. Run the script to try all the bibcodes in a directory. 
#       - python3 automate_building_dockerfiles.py dir/ , eg. python3 automate_building_dockerfiles.py .
# 2. Run it for a particular bibcode.
#       - python3 automate_building_dockerfiles.py . --bibcode RosuS12
#
#   Script is going to 
#   a) Find Bibcodes/Dockerfiles in the given directory
#   b) Build Dockerfile for given ubuntu version. 
#   c) If the build fails, send Dockerfile and error logs to Llama API and recieve an updated Dockerfile as result.
#   d) Retry upto (max_retries=3) for the updated Dockerfiles.
#   e) Log all steps details in log file
#   f) Log results in csv file which we will use to analyze results.
#
# Sample output,
# -------------------------
# Processing Bibcode 'RosuS12' with Ubuntu '14.04'...
# Updated Dockerfile written to ./RosuS12/Dockerfile_14.04
# Build logs written to ./RosuS12/build_log_1404.txt
# Test Results for image 'rosus12:1404': 1 passed, 0 failed.
#
# Processing Bibcode 'RosuS12' with Ubuntu '16.04'...
# Updated Dockerfile written to ./RosuS12/Dockerfile_16.04
# Build logs written to ./RosuS12/build_log_1604.txt
# Build failed for image 'rosus12:1604'. Attempting to fix Dockerfile via LLM API (Retry 1/3).
# Fixed Dockerfile written to ./RosuS12/Dockerfile_16.04_fixed_1
# Fixed build logs written to ./RosuS12/build_log_1604_fixed_1.txt
# Build succeeded for image 'rosus12:1604' after applying fix.
# Test Results for image 'rosus12:1604': 1 passed, 0 failed.
#
# Processing Bibcode 'RosuS12' with Ubuntu '18.04'...
# Updated Dockerfile written to ./RosuS12/Dockerfile_18.04
# Build logs written to ./RosuS12/build_log_1804.txt
# Build failed for image 'rosus12:1804'. Attempting to fix Dockerfile via LLM API (Retry 1/3).
# Fixed Dockerfile written to ./RosuS12/Dockerfile_18.04_fixed_1
# Fixed build logs written to ./RosuS12/build_log_1804_fixed_1.txt
# Build succeeded for image 'rosus12:1804' after applying fix.
# Test Results for image 'rosus12:1804': 1 passed, 0 failed.
# 
# Processing Bibcode 'RosuS12' with Ubuntu '20.04'...
# Updated Dockerfile written to ./RosuS12/Dockerfile_20.04
# Build logs written to ./RosuS12/build_log_2004.txt
# Build failed for image 'rosus12:2004'. Attempting to fix Dockerfile via LLM API (Retry 1/3).
# Fixed Dockerfile written to ./RosuS12/Dockerfile_20.04_fixed_1
# Fixed build logs written to ./RosuS12/build_log_2004_fixed_1.txt
# Build succeeded for image 'rosus12:2004' after applying fix.
# Test Results for image 'rosus12:2004': 1 passed, 0 failed.
# 
# Processing Bibcode 'RosuS12' with Ubuntu '22.04'...
# Updated Dockerfile written to ./RosuS12/Dockerfile_22.04
# Build logs written to ./RosuS12/build_log_2204.txt
# Build failed for image 'rosus12:2204'. Attempting to fix Dockerfile via LLM API (Retry 1/3).
# Fixed Dockerfile written to ./RosuS12/Dockerfile_22.04_fixed_1
# Fixed build logs written to ./RosuS12/build_log_2204_fixed_1.txt
# Build succeeded for image 'rosus12:2204' after applying fix.
# Test Results for image 'rosus12:2204': 1 passed, 0 failed.
# 
# Processing Bibcode 'RosuS12' with Ubuntu '24.04'...
# Updated Dockerfile written to ./RosuS12/Dockerfile_24.04
# Build logs written to ./RosuS12/build_log_2404.txt
# Build failed for image 'rosus12:2404'. Attempting to fix Dockerfile via LLM API (Retry 1/3).
# Fixed Dockerfile written to ./RosuS12/Dockerfile_24.04_fixed_1
# Fixed build logs written to ./RosuS12/build_log_2404_fixed_1.txt
# Build failed for image 'rosus12:2404' after applying fix.
# Build failed for image 'rosus12:2404'. Attempting to fix Dockerfile via LLM API (Retry 2/3).
# LLM failed to provide a fixed Dockerfile for image 'rosus12:2404'.
# Build failed for image 'rosus12:2404' after 3 retries.
#
######################################


import os
import re
import docker
import csv
from datetime import datetime
import argparse
import logging
import requests
import json
import time

logging.basicConfig(
    filename='docker_build.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)

client = docker.from_env()

UBUNTU_VERSIONS = ['14.04','16.04', '18.04', '20.04', '22.04', '24.04']

CSV_FILE = 'results.csv'

HUGGINGFACE_API_URL = "https://api-inference.huggingface.co/models/meta-llama/Llama-3.2-3B-Instruct"

HUGGINGFACE_API_TOKEN = os.getenv('HUGGINGFACE_API_TOKEN')
if not HUGGINGFACE_API_TOKEN:
    logging.critical("HUGGINGFACE_API_TOKEN environment variable not set.")
    raise EnvironmentError("HUGGINGFACE_API_TOKEN environment variable not set.")

HEADERS = {
    "Authorization": f"Bearer {HUGGINGFACE_API_TOKEN}",
    "Content-Type": "application/json"
}

def parse_arguments():
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description='Automate Docker builds for multiple Bibcodes.')
    parser.add_argument('directory', help='Path to the directory containing Bibcode subdirectories.')
    parser.add_argument('-b', '--bibcode', help='Specific Bibcode to build. Builds all if not provided.', default=None, required=False)
    return parser.parse_args()

def load_bibcode_directories(base_directory, specific_bibcode=None):
    """
    Loads Bibcode subdirectories from the given directory.
    If specific_bibcode is provided, validates and returns only that Bibcode.
    """
    all_dirs = [d for d in os.listdir(base_directory) if os.path.isdir(os.path.join(base_directory, d))]
    
    if specific_bibcode:
        if specific_bibcode in all_dirs:
            logging.info(f"Specific Bibcode '{specific_bibcode}' found. Proceeding with build.")
            return [specific_bibcode]
        else:
            logging.error(f"Specified Bibcode '{specific_bibcode}' not found in directory '{base_directory}'.")
            print(f"Error: Specified Bibcode '{specific_bibcode}' not found.")
            return []
    else:
        logging.info(f"Found {len(all_dirs)} Bibcode(s) in directory '{base_directory}'. Proceeding with builds.")
        return all_dirs

def read_dockerfile(dockerfile_path):
    """Reads the content of a Dockerfile."""
    with open(dockerfile_path, 'r') as f:
        return f.read()

def extract_base_version(dockerfile_content):
    """Extracts the base Ubuntu version from a Dockerfile."""
    match = re.search(r'FROM\s+ubuntu:(\S+)', dockerfile_content)
    return match.group(1) if match else None

def update_dockerfile_content(dockerfile_content, ubuntu_version):
    """Updates the Dockerfile content with the specified Ubuntu version."""
    return re.sub(r'FROM\s+ubuntu:\S+', f'FROM ubuntu:{ubuntu_version}', dockerfile_content)

def sanitize_image_tag(tag):
    """Sanitize the image tag to conform to Docker naming conventions."""
    sanitized_tag = re.sub(r'[^a-zA-Z0-9_.-]', '_', tag).lower()
    return sanitized_tag

def build_image(dockerfile_name, image_tag, build_context):
    """Builds the Docker image with the specified tag."""
    try:
        logging.info(f"Starting build for image: {image_tag} using Dockerfile: {dockerfile_name}")
        image, build_logs = client.images.build(
            path=build_context,
            dockerfile=dockerfile_name,
            tag=image_tag,
            rm=True,
            pull=False
        )
        build_logs_text = [line.get('stream', '') for line in build_logs]
        logging.info(f"Successfully built image: {image_tag}")
        return True, None, build_logs_text
    except docker.errors.BuildError as build_err:
        build_logs_text = [line.get('stream', '') for line in build_err.build_log]
        error_message = ''.join(build_logs_text)
        logging.error(f"BuildError for image {image_tag}: {error_message}")
        return False, error_message, build_logs_text
    except Exception as e:
        logging.error(f"Unexpected error during build for image {image_tag}: {e}")
        return False, str(e), []

def run_container(image_tag):
    """Runs the Docker container and captures the output."""
    container = None
    try:
        logging.info(f"Running container for image: {image_tag}")
        container = client.containers.run(image_tag, detach=True)
        exit_status = container.wait()
        logs = container.logs().decode('utf-8')
        logging.info(f"Container run completed for image: {image_tag}")
        return True, logs
    except Exception as e:
        logging.error(f"Error running container for image {image_tag}: {e}")
        return False, str(e)
    finally:
        if container:
            try:
                container.remove(force=True)
                logging.info(f"Removed container for image: {image_tag}")
            except Exception as e:
                logging.error(f"Error removing container for image {image_tag}: {e}")

def parse_test_results(logs):
    """Parses the test results from the container logs."""
    pass_pattern = r'Tests Passed:\s*(\d+)'
    fail_pattern = r'Tests Failed:\s*(\d+)'
    
    passed = re.search(pass_pattern, logs)
    failed = re.search(fail_pattern, logs)
    
    passed_cases = int(passed.group(1)) if passed else 1
    failed_cases = int(failed.group(1)) if failed else 0
    
    total_cases = passed_cases + failed_cases
    pass_percentage = (passed_cases / total_cases) * 100 if total_cases > 0 else 0
    
    return passed_cases, failed_cases, pass_percentage

def log_results(data, csv_file):
    """Appends the data to the CSV file."""
    file_exists = os.path.isfile(csv_file)
    with open(csv_file, 'a', newline='') as csvfile:
        fieldnames = [
            'S. No.',
            'Bibcode',
            'Base Version',
            'Updated Ubuntu Version',
            'Cases Passed',
            'Cases Failed',
            'Pass Percentage',
            'Error Details',
            'Modifications to Dockerfile'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(data)

def fix_dockerfile_with_llm(dockerfile_content, error_logs):
    """
    Sends the Dockerfile and error logs to Huggingface LLM API and retrieves the fixed Dockerfile.
    
    Args:
        dockerfile_content (str): The content of the failed Dockerfile.
        error_logs (str): The last 200 lines of error logs.
        
    Returns:
        str: The fixed Dockerfile content if successful, else None.
    """
    prompt = f"The following Dockerfile failed to build due to the errors listed below. Please analyze the Dockerfile and the error logs, \
        and provide a corrected version of the Dockerfile. Only return the fixed Dockerfile without any additional text. Make sure to give space after RUN Command. \
        Dockerfile:\n{dockerfile_content} Error Logs:\n{error_logs}. Fixed Dockerfile:"
    
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 2000,
            "temperature": 0.2,
            "stop": ["Fixed Dockerfile:"]
        }
    }
    
    try:
        logging.info("Sending Dockerfile and error logs to Huggingface LLM API for fixing.")
        response = requests.post(
            HUGGINGFACE_API_URL,
            headers=HEADERS,
            data=json.dumps(payload)
        )
        
        if response.status_code != 200:
            logging.error(f"Huggingface API request failed with status code {response.status_code}: {response.text}")
            return None
        
        response_json = response.json()
        if 'error' in response_json:
            logging.error(f"Huggingface API returned an error: {response_json['error']}")
            return None
        
        generated_text = response_json[0].get('generated_text', '').strip()
        
        if not generated_text:
            logging.error("Huggingface API did not return any generated text.")
            return None
        
        # Extract the fixed Dockerfile after 'Fixed Dockerfile:'
        delimiter = "Fixed Dockerfile:"
        if delimiter in generated_text:
            fixed_dockerfile = generated_text.split(delimiter, 1)[1].strip()
        else:
            fixed_dockerfile = generated_text
        
        delimiter = "Note:"
        if delimiter in fixed_dockerfile:
            fixed_dockerfile = fixed_dockerfile.split(delimiter, 1)[0].strip()

        delimiter = "Note that"
        if delimiter in fixed_dockerfile:
            fixed_dockerfile = fixed_dockerfile.split(delimiter, 1)[0].strip()


        if not fixed_dockerfile.startswith("FROM "):
            logging.warning("Fixed Dockerfile does not start with 'FROM '. Validating and proceeding.")
        
        logging.info("Received fixed Dockerfile from Huggingface LLM API.")
        return fixed_dockerfile
    
    except Exception as e:
        logging.error(f"Exception occurred while communicating with Huggingface API: {e}")
        return None

def main():
    args = parse_arguments()
    base_directory = args.directory
    specific_bibcode = args.bibcode
    print(specific_bibcode)

    serial_no = 1

    # Get list of Bibcode subdirectories
    bibcode_dirs = load_bibcode_directories(base_directory, specific_bibcode)

    if specific_bibcode and not bibcode_dirs:
        logging.critical(f"Specified Bibcode '{specific_bibcode}' not found. Exiting.")
        return

    for bibcode in bibcode_dirs:
        bibcode_dir = os.path.join(base_directory, bibcode)
        dockerfile_path = os.path.join(bibcode_dir, 'Dockerfile')
        
        if not os.path.exists(dockerfile_path):
            logging.warning(f"Dockerfile not found for Bibcode {bibcode}. Skipping.")
            print(f"Dockerfile not found for Bibcode '{bibcode}'. Skipping.")
            continue

        # Read the base Dockerfile
        try:
            dockerfile_content = read_dockerfile(dockerfile_path)
            logging.info(f"Read Dockerfile for Bibcode {bibcode}.")
        except Exception as e:
            logging.error(f"Error reading Dockerfile for Bibcode {bibcode}: {e}")
            continue

        # Extract the base Ubuntu version
        base_version = extract_base_version(dockerfile_content)
        if not base_version:
            logging.warning(f"Could not find base Ubuntu version in Dockerfile for Bibcode {bibcode}. Skipping.")
            print(f"Could not find base Ubuntu version in Dockerfile for Bibcode '{bibcode}'. Skipping.")
            continue

        for ubuntu_version in UBUNTU_VERSIONS:
            logging.info(f"Processing Bibcode {bibcode} with Ubuntu {ubuntu_version}...")
            print(f"\nProcessing Bibcode '{bibcode}' with Ubuntu '{ubuntu_version}'...")

            # Update the Dockerfile content with the new Ubuntu version
            updated_dockerfile_content = update_dockerfile_content(dockerfile_content, ubuntu_version)

            if not updated_dockerfile_content.strip():
                logging.warning(f"Updated Dockerfile content is empty for {bibcode} with Ubuntu {ubuntu_version}. Skipping.")
                print(f"Updated Dockerfile content is empty for Bibcode '{bibcode}' with Ubuntu '{ubuntu_version}'. Skipping.")
                continue

            # Write the updated Dockerfile to a temporary file
            temp_dockerfile_name = f'Dockerfile_{ubuntu_version}'  # Retain the dot
            temp_dockerfile_path = os.path.join(bibcode_dir, temp_dockerfile_name)

            try:
                with open(temp_dockerfile_path, 'w') as f:
                    f.write(updated_dockerfile_content)
                logging.info(f"Updated Dockerfile written to {temp_dockerfile_path}")
                print(f"Updated Dockerfile written to {temp_dockerfile_path}")
            except Exception as e:
                logging.error(f"Error writing Dockerfile {temp_dockerfile_path}: {e}")
                print(f"Error writing Dockerfile '{temp_dockerfile_path}': {e}")
                continue

            # Sanitize the bibcode for use in image tag
            sanitized_bibcode = sanitize_image_tag(bibcode)

            # Build the image
            image_tag = f'{sanitized_bibcode}:{ubuntu_version.replace(".", "")}'
            success, error_message, build_logs = build_image(temp_dockerfile_name, image_tag, bibcode_dir)
            
            # Store last 200 lines of build logs in a log file
            log_file_name = f'build_log_{ubuntu_version.replace(".", "")}.txt'
            log_file_path = os.path.join(bibcode_dir, log_file_name)
            try:
                with open(log_file_path, 'w') as log_file:
                    log_file.writelines(build_logs[-200:])
                logging.info(f"Build logs written to {log_file_path}")
                print(f"Build logs written to {log_file_path}")
            except Exception as e:
                logging.error(f"Error writing build logs to {log_file_path}: {e}")
                print(f"Error writing build logs to '{log_file_path}': {e}")

            retry_count = 0
            max_retries = 3

            while not success and retry_count < max_retries:
                logging.info(f"Build failed for image {image_tag}. Attempting to fix Dockerfile via LLM API (Retry {retry_count + 1}/{max_retries}).")
                print(f"Build failed for image '{image_tag}'. Attempting to fix Dockerfile via LLM API (Retry {retry_count + 1}/{max_retries}).")

                # Prepare error logs
                error_logs = ''.join(build_logs[-200:])

                # Attempt to fix the Dockerfile using LLM
                fixed_dockerfile_content = fix_dockerfile_with_llm(updated_dockerfile_content, error_logs)

                if not fixed_dockerfile_content:
                    logging.error(f"LLM failed to provide a fixed Dockerfile for image {image_tag}.")
                    print(f"LLM failed to provide a fixed Dockerfile for image '{image_tag}'.")
                    break  # Exit the retry loop

                # Write the fixed Dockerfile to a new file
                fixed_dockerfile_name = f'Dockerfile_{ubuntu_version}_fixed_{retry_count + 1}'
                fixed_dockerfile_path = os.path.join(bibcode_dir, fixed_dockerfile_name)

                try:
                    with open(fixed_dockerfile_path, 'w') as f:
                        f.write(fixed_dockerfile_content)
                    logging.info(f"Fixed Dockerfile written to {fixed_dockerfile_path}")
                    print(f"Fixed Dockerfile written to {fixed_dockerfile_path}")
                except Exception as e:
                    logging.error(f"Error writing fixed Dockerfile {fixed_dockerfile_path}: {e}")
                    print(f"Error writing fixed Dockerfile '{fixed_dockerfile_path}': {e}")
                    break

                # Build the image with the fixed Dockerfile
                success, error_message, build_logs = build_image(fixed_dockerfile_name, image_tag, bibcode_dir)
                
                # Store last 200 lines of build logs in a log file
                fixed_log_file_name = f'build_log_{ubuntu_version.replace(".", "")}_fixed_{retry_count + 1}.txt'
                fixed_log_file_path = os.path.join(bibcode_dir, fixed_log_file_name)
                try:
                    with open(fixed_log_file_path, 'w') as log_file:
                        log_file.writelines(build_logs[-200:])
                    logging.info(f"Fixed build logs written to {fixed_log_file_path}")
                    print(f"Fixed build logs written to {fixed_log_file_path}")
                except Exception as e:
                    logging.error(f"Error writing fixed build logs to {fixed_log_file_path}: {e}")
                    print(f"Error writing fixed build logs to '{fixed_log_file_path}': {e}")

                if success:
                    logging.info(f"Build succeeded for image {image_tag} after applying fix.")
                    print(f"Build succeeded for image '{image_tag}' after applying fix.")
                else:
                    logging.warning(f"Build failed for image {image_tag} after applying fix.")
                    print(f"Build failed for image '{image_tag}' after applying fix.")
                
                retry_count += 1
                time.sleep(2)

            if success:
                # Run the container and capture output
                run_success, output = run_container(image_tag)
                if run_success:
                    # Parse test results
                    passed_cases, failed_cases, pass_percentage = parse_test_results(output)
                    # Log results
                    data = {
                        'S. No.': serial_no,
                        'Bibcode': bibcode,
                        'Base Version': base_version,
                        'Updated Ubuntu Version': ubuntu_version,
                        'Cases Passed': passed_cases,
                        'Cases Failed': failed_cases,
                        'Pass Percentage': pass_percentage,
                        'Error Details': '',
                        'Modifications to Dockerfile': ''
                    }
                    log_results(data, CSV_FILE)
                    serial_no += 1
                    logging.info(f"Test Results for {image_tag}: {passed_cases} passed, {failed_cases} failed.")
                    print(f"Test Results for image '{image_tag}': {passed_cases} passed, {failed_cases} failed.")
                else:
                    logging.error(f"Error running container for image {image_tag}: {output}")
                    print(f"Error running container for image '{image_tag}': {output}")
                    # Log failure
                    data = {
                        'S. No.': serial_no,
                        'Bibcode': bibcode,
                        'Base Version': base_version,
                        'Updated Ubuntu Version': ubuntu_version,
                        'Cases Passed': 0,
                        'Cases Failed': 0,
                        'Pass Percentage': 0,
                        'Error Details': output,
                        'Modifications to Dockerfile': ''
                    }
                    log_results(data, CSV_FILE)
                    serial_no += 1
            else:
                logging.error(f"Build failed for image {image_tag} after {max_retries} retries.")
                print(f"Build failed for image '{image_tag}' after {max_retries} retries.")
                # Log failure
                data = {
                    'S. No.': serial_no,
                    'Bibcode': bibcode,
                    'Base Version': base_version,
                    'Updated Ubuntu Version': ubuntu_version,
                    'Cases Passed': 0,
                    'Cases Failed': 0,
                    'Pass Percentage': 0,
                    'Error Details': error_message[:-5],
                    'Modifications to Dockerfile': f"Attempted fixes via LLM API, {retry_count} retries"
                }
                log_results(data, CSV_FILE)
                serial_no += 1

if __name__ == '__main__':
    main()
