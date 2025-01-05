from flask import Flask, render_template, abort
import logging
from scraper import init_db, scrape_models, get_models, get_model_by_slug

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def initialize_data():
    """Initialize database and scrape models"""
    try:
        logger.info("Initializing database...")
        init_db()
        logger.info("Scraping models...")
        models = scrape_models()
        logger.info(f"Successfully scraped {len(models)} models")
        return True
    except Exception as e:
        logger.error(f"Error initializing data: {str(e)}")
        return False

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/models')
def models():
    try:
        # Get models from database
        model_list = get_models()
        logger.info(f"Retrieved {len(model_list)} models from database")
        return render_template('models.html', models=model_list)
    except Exception as e:
        logger.error(f"Error retrieving models: {str(e)}")
        return render_template('models.html', models=[])

@app.route('/model/<slug>')
def model_detail(slug):
    try:
        model = get_model_by_slug(slug)
        if model is None:
            logger.warning(f"Model not found with slug: {slug}")
            abort(404)
        return render_template('model_detail.html', model=model)
    except Exception as e:
        logger.error(f"Error retrieving model details: {str(e)}")
        abort(500)

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    # Initialize data before starting the server
    if initialize_data():
        logger.info("Starting Flask server...")
        app.run(debug=True, port=5001)
    else:
        logger.error("Failed to initialize data. Please check the logs and try again.")