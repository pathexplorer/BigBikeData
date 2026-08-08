# Safety
NEVER use `rm -rf` or any forced recursive deletion. Use safe alternatives like `mv` to a trash directory if cleanup is needed.
# Instruments
## Conteinerization
### Local testing 
I use Podman and podman-compose in rootless mode (not standard Docker). Ensure all container configs, permissions, and volume mounts account for Podman's architecture. Podman not support short-name: the images needs the full registry path.
### Production 
I use Google Cloud Platphorm, and for cloud deployment we need use Docker syntax 

# Documentation
## Maintance documentation
After succesfull complete some task, update certain README.MD for this new changes.
## Reproducibility
Not use in instruction phrases such as "paste_your_project_id_there". If instruction needs this project ID, it must set as environment variable at first step  

# Security
## keys location
Dont store API keys and tokens as plain text at disk. Propose using encrypted solution