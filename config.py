import os

# Get the base directory of the Flask application
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Path to the directory where FITS files are stored
FITS_FILES_DIR = os.path.join(BASE_DIR, 'fits_files')

# Flask secret key (important for sessions and security)
# In a real application, this should be a complex, randomly generated string
# and stored securely (e.g., environment variable).
SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-very-secret-and-random-key'

# You can add more configuration variables here later
DEBUG = True # Set to False in production!
