# Use a slim Python base image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy only requirements.txt first
COPY requirements.txt .   

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download NLTK data files
RUN mkdir -p /usr/share/nltk_data 
RUN python -m nltk.downloader -d /usr/share/nltk_data punkt_tab stopwords

# Copy utils and dynamics manager
COPY utils.py ./utils.py
COPY dynamics_manager.py ./dynamics_manager.py
COPY relevance_prompt_examples.py ./relevance_prompt_examples.py

# Entrypoint for your pipeline
CMD ["python", "tuning_pipeline.py"]