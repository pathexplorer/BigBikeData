# import os
# from pathlib import Path
#
# def get_expanded_path(env_var_name: str) -> Path:
#     """
#     Retrieves a path from an environment variable and ensures
#     any $HOME or ~ prefixes are expanded to the user's home directory.
#     This function handles the path resolution for ALL code.
#     """
#     try:
#         raw_path = os.environ[env_var_name]
#     except KeyError:
#         raise ValueError(f"🯀 ERROR: Required environment variable '{env_var_name}' is not set.")
#
#     expanded_path = Path(raw_path).expanduser()
#
#     if not expanded_path.is_absolute():
#         print(f"🯀 WARNING: Path '{raw_path}' is still relative. Resolving...")
#         return expanded_path.resolve()
#
#     return expanded_path
#
#
#
# if __name__ == "__main__":
#     # Ensure environment variables are loaded (e.g., using python-dotenv)
#     # load_dotenv()
#
#     # You only need to call the getter function; the Path object is ready to use.
#     try:
#         cred_file_path: Path = get_expanded_path("GOOGLE_APPLICATION_CREDENTIALS")
#
#
#
#     except ValueError as e:
#         print(e)