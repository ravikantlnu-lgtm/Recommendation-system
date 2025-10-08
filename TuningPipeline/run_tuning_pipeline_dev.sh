#!/bin/bash

# Set up environment variables
PROJECT_ID="proj-sales-recommender-dev" 
LOCATION="us-central1"
IMAGE_URI="$LOCATION-docker.pkg.dev/$PROJECT_ID/model-tuning/components"
SERVICE_ACCOUNT="195063057478-compute@developer.gserviceaccount.com"
echo "ENV_FILE: $ENV_FILE"


# Build and push Dockerfile
cp ../CloudFunction/services/dynamics_manager.py ./dynamics_manager.py
cp ../CloudFunction/utils/relevance_prompt_examples.py ./relevance_prompt_examples.py
docker build --no-cache -t $IMAGE_URI:latest . --platform linux/amd64
docker push $IMAGE_URI

# Compile components using latest image
python components/_compile_components.py --latest_image_name $IMAGE_URI

# Setup tuning args and save configuration file
CONFIG_FILE=$(python setup_tuning_args.py)

# Run tuning pipeline
python tuning_pipeline.py --config_path $CONFIG_FILE --service_account $SERVICE_ACCOUNT



