from flask import Flask, render_template, abort, url_for, redirect, request
import logging
from scraper import init_db, scrape_models, get_models, get_model_by_slug
import threading
import sqlite3
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='/static')

# Global variable to track total models being scraped
total_models_to_scrape = 0

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

# Start data initialization in a background thread
init_thread = threading.Thread(target=initialize_data)
init_thread.daemon = True
init_thread.start()

@app.route('/')
def home():
    breadcrumbs = []  # Home page has no breadcrumbs
    return render_template('index.html', breadcrumbs=breadcrumbs)

@app.route('/models')
def models():
    try:
        # Get page number from query parameters, default to 1
        page = int(request.args.get('page', 1))
        per_page = 20
        
        # Set breadcrumbs
        breadcrumbs = [
            {'url': '/models', 'text': 'Models'}
        ]
        
        # Get models from database
        logger.info("Fetching models from database...")
        model_list = get_models()
        
        # Only show models that have been fully downloaded
        available_models = [
            model for model in model_list
            if model.get('providers') and model.get('provider_details') and model.get('description')
        ]
        
        # Sort models, prioritizing Deepseek V3 models
        def sort_key(model):
            name = model['name'].lower()
            model_id = model['model_id'].lower()
            if 'deepseek' in name and 'v3' in name:
                return ('0', name)  # '0' prefix to ensure Deepseek V3 comes first
            elif 'codestral' in model_id and 'mamba' in model_id:
                return ('1', name)  # '1' prefix to ensure Codestral Mamba comes second
            return ('2', name)
        
        available_models.sort(key=sort_key)
        
        # Calculate pagination
        total_models = len(available_models)
        total_pages = (total_models + per_page - 1) // per_page
        
        # Ensure page is within valid range
        page = max(1, min(page, total_pages))
        
        # Slice the models list for current page
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_models = available_models[start_idx:end_idx]
        
        # Get total models being scraped
        global total_models_to_scrape
        if total_models_to_scrape == 0:
            try:
                # Check if database exists
                if os.path.exists('models.db'):
                    conn = sqlite3.connect('models.db')
                    c = conn.cursor()
                    c.execute('SELECT COUNT(*) FROM models')
                    total_models_to_scrape = c.fetchone()[0] or 217  # Default to 217 if no count
                    conn.close()
                else:
                    total_models_to_scrape = 217  # Default number of models
            except:
                total_models_to_scrape = 217  # Default if database error
        
        logger.info(f"Retrieved {len(available_models)} available models out of {total_models_to_scrape} total models")
        for model in available_models:
            logger.info(f"Model: {model['name']}, Providers: {model['providers']}")
        
        return render_template(
            'models.html',
            models=paginated_models,
            total_models=total_models_to_scrape,
            available_models=len(available_models),
            breadcrumbs=breadcrumbs,
            current_page=page,
            total_pages=total_pages,
            per_page=per_page
        )
    except Exception as e:
        logger.error(f"Error retrieving models: {str(e)}")
        logger.exception(e)  # This will log the full stack trace
        return render_template('models.html', models=[], total_models=217, available_models=0, breadcrumbs=breadcrumbs)

@app.route('/model/<slug>')
def model_detail(slug):
    try:
        logger.info(f"Fetching details for model: {slug}")
        model = get_model_by_slug(slug)
        if model is None:
            logger.warning(f"Model not found with slug: {slug}")
            abort(404)
        
        # Set breadcrumbs
        breadcrumbs = [
            {'url': '/models', 'text': 'Models'},
            {'url': f'/model/{slug}', 'text': model['name']}
        ]
        
        logger.info(f"Found model: {model['name']}")
        return render_template('model_detail.html', model=model, breadcrumbs=breadcrumbs)
    except Exception as e:
        logger.error(f"Error retrieving model details: {str(e)}")
        logger.exception(e)  # This will log the full stack trace
        abort(500)

@app.route('/admin')
def admin():
    try:
        # Set breadcrumbs
        breadcrumbs = [
            {'url': '/admin', 'text': 'Admin'}
        ]
        
        # Get models count
        model_list = get_models()
        available_models = [
            model for model in model_list
            if model.get('providers') and model.get('provider_details') and model.get('description')
        ]
        
        return render_template(
            'admin.html',
            total_models=total_models_to_scrape,
            available_models=len(available_models),
            breadcrumbs=breadcrumbs
        )
    except Exception as e:
        logger.error(f"Error accessing admin page: {str(e)}")
        logger.exception(e)
        abort(500)

@app.route('/admin/refresh', methods=['POST'])
def refresh_models():
    try:
        # Reset the database and start scraping again
        logger.info("Refreshing models database...")
        initialize_data()
        return redirect('/admin')
    except Exception as e:
        logger.error(f"Error refreshing models: {str(e)}")
        logger.exception(e)
        abort(500)

@app.errorhandler(404)
def not_found_error(error):
    breadcrumbs = [{'url': '#', 'text': 'Not Found'}]
    return render_template('404.html', breadcrumbs=breadcrumbs), 404

@app.errorhandler(500)
def internal_error(error):
    breadcrumbs = [{'url': '#', 'text': 'Error'}]
    return render_template('500.html', breadcrumbs=breadcrumbs), 500

if __name__ == '__main__':
    # Ensure static directory exists
    os.makedirs('static/css', exist_ok=True)
    
    # Start the Flask server immediately
    logger.info("Starting Flask server on port 5000...")
    app.run(host='127.0.0.1', port=5000, debug=True)