from flask import Flask, render_template, abort, url_for, redirect, request, send_file
import logging
from scraper import (
    init_db, scrape_models, get_models, get_model_by_slug,
    get_rankings_by_category, get_all_apps, scrape_rankings, store_ranking_data,
    scrape_apps, store_app_data
)
import threading
import concurrent.futures
import sqlite3
import os
import csv
import io

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='/static')

# Global variables to track scraping status
is_scraping = False
should_stop_scraping = False
total_models_to_scrape = 0

def initialize_database():
    """Initialize database only"""
    try:
        logger.info("Initializing database...")
        init_db()  # Creates table if it doesn't exist
        return True
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        return False

# --- Helper functions for concurrent scraping ---
def scrape_and_store_models_task(stop_check):
    logger.info("Starting model scraping task...")
    try:
        models = scrape_models(stop_check)
        if not stop_check():
            logger.info(f"Finished scraping {len(models)} models.")
        else:
            logger.info("Model scraping task stopped.")
    except Exception as e:
        logger.error(f"Error in model scraping task: {e}")
        logger.exception(e)

def scrape_and_store_rankings_task(stop_check):
    logger.info("Starting ranking scraping task...")
    try:
        categories_to_scrape = ['general', 'roleplay', 'programming']
        all_rankings = []
        for category in categories_to_scrape:
            if stop_check():
                logger.info("Ranking scraping task stopped during category loop.")
                return
            logger.info(f"Scraping '{category}' rankings...")
            rankings = scrape_rankings(category=category, view='week')
            all_rankings.extend(rankings)

        if not stop_check():
            store_ranking_data(all_rankings)
            logger.info("Finished scraping and storing rankings.")
        else:
            logger.info("Ranking scraping task stopped before storing.")
    except Exception as e:
        logger.error(f"Error in ranking scraping task: {e}")
        logger.exception(e)

def scrape_and_store_apps_task(stop_check):
    logger.info("Starting app scraping task...")
    try:
        apps = scrape_apps()
        if not stop_check():
            store_app_data(apps)
            logger.info("Finished scraping and storing apps.")
        else:
            logger.info("App scraping task stopped.")
    except Exception as e:
        logger.error(f"Error in app scraping task: {e}")
        logger.exception(e)
# --- End Helper functions ---

        return True
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        return False
def start_scraping():
    """Start scraping models in a background thread"""
    global is_scraping, should_stop_scraping, total_models_to_scrape
    
    def scrape_worker():
        global is_scraping, should_stop_scraping
        try:
            is_scraping = True
            should_stop_scraping = False
            logger.info("Starting concurrent full scrape process...")

            # Define the tasks to run concurrently
            tasks = [
                scrape_and_store_models_task,
                scrape_and_store_rankings_task,
                scrape_and_store_apps_task
            ]

            # Use ThreadPoolExecutor to run tasks concurrently
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as executor:
                # Pass the stop check lambda to each task
                stop_check = lambda: should_stop_scraping
                futures = [executor.submit(task, stop_check) for task in tasks]

                # Wait for all tasks to complete (or be stopped)
                # concurrent.futures.wait(futures) # No need to explicitly wait if just logging completion

            if should_stop_scraping:
                logger.info("Full scraping process was stopped by user.")
            else:
                logger.info("Full scraping process completed (or tasks finished).")

        except Exception as e:
            logger.error(f"Error during concurrent scraping process: {str(e)}")
            logger.exception(e)
        finally:
            is_scraping = False
            # Reset stop flag regardless of completion status
            should_stop_scraping = False
            logger.info("Scraping worker finished.")
    
    if not is_scraping:
        thread = threading.Thread(target=scrape_worker)
        thread.daemon = True
        thread.start()
        return True
    return False

@app.route('/admin/stop', methods=['POST'])
def stop_scraping():
    """Stop the scraping process"""
    global should_stop_scraping
    try:
        logger.info("Stopping scraping process...")
        should_stop_scraping = True
        return redirect('/admin')
    except Exception as e:
        logger.error(f"Error stopping scrape: {str(e)}")
        logger.exception(e)
        abort(500)

@app.route('/admin/delete', methods=['POST'])
def delete_models():
    """Delete all models from the database"""
    try:
        logger.info("Deleting all models from database...")
        conn = sqlite3.connect('models.db')
        c = conn.cursor()
        c.execute('DELETE FROM models')
        conn.commit()
        conn.close()
        logger.info("Successfully deleted all models")
        return redirect('/admin')
    except Exception as e:
        logger.error(f"Error deleting models: {str(e)}")
        logger.exception(e)
        abort(500)
    return False

# Initialize database on startup (without scraping)
initialize_database()

@app.route('/')
def home():
    breadcrumbs = []  # Home page has no breadcrumbs
    return render_template('index.html', breadcrumbs=breadcrumbs)

@app.route('/models')
def models():
    try:
        # Get search query and page number from query parameters
        search_query = request.args.get('q', '').lower()
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
        
        # Filter models if search query exists
        if search_query:
            filtered_models = []
            for model in available_models:
                name = model['name'].lower()
                model_id = model['model_id'].lower()
                providers = [p.lower() for p in model['providers']]
                if (search_query in name or
                    search_query in model_id or
                    any(search_query in p for p in providers)):
                    filtered_models.append(model)
            available_models = filtered_models
        
        # Sort models, prioritizing newer models
        def sort_key(model):
            name = model['name'].lower()
            model_id = model['model_id'].lower()
            if 'claude-3' in model_id:
                return ('0', name)  # Claude-3 models first
            elif 'gpt-4' in model_id:
                return ('1', name)  # GPT-4 models second
            elif 'gemini' in model_id:
                return ('2', name)  # Gemini models third
            return ('3', name)  # All other models
        
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

        # Return the rendered template with paginated models and other data
        return render_template(
            'models.html',
            models=paginated_models,
            total_models=total_models_to_scrape,
            available_models=len(available_models),
            breadcrumbs=breadcrumbs,
            current_page=page,
            total_pages=total_pages,
            per_page=per_page,
            is_scraping=is_scraping  # Pass scraping status to template
        )
    except Exception as e:
        logger.error(f"Error retrieving models: {str(e)}")
        logger.exception(e)  # This will log the full stack trace
        # Ensure breadcrumbs is defined even in case of error before rendering
        breadcrumbs = [{'url': '/models', 'text': 'Models'}] # Define breadcrumbs here for the error case
        # Return error template or a simplified models page
        return render_template('models.html', models=[], total_models=0, available_models=0, breadcrumbs=breadcrumbs, is_scraping=is_scraping, current_page=1, total_pages=1, error=str(e))

@app.route('/rankings')
def rankings():
    try:
        category = request.args.get('category', 'general') # Default to general
        valid_categories = ['general', 'roleplay', 'programming']
        if category not in valid_categories:
            category = 'general' # Fallback to general if invalid

        logger.info(f"Fetching rankings for category: {category}")
        ranking_list = get_rankings_by_category(category)

        breadcrumbs = [
            {'url': '/rankings', 'text': 'Rankings'},
            {'url': f'/rankings?category={category}', 'text': category.capitalize()}
        ]

        return render_template(
            'rankings.html',
            rankings=ranking_list,
            current_category=category,
            categories=valid_categories,
            breadcrumbs=breadcrumbs
        )
    except Exception as e:
        logger.error(f"Error retrieving rankings: {str(e)}")
        logger.exception(e)
        abort(500)

@app.route('/apps')
def apps():
    try:
        logger.info("Fetching app showcase data...")
        app_list = get_all_apps()

        breadcrumbs = [
            {'url': '/apps', 'text': 'App Showcase'}
        ]

        return render_template('apps.html', apps=app_list, breadcrumbs=breadcrumbs)
    except Exception as e:
        logger.error(f"Error retrieving apps: {str(e)}")
        logger.exception(e)
        abort(500)

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
            breadcrumbs=breadcrumbs,
            is_scraping=is_scraping  # Pass scraping status to template
        )
    except Exception as e:
        logger.error(f"Error accessing admin page: {str(e)}")
        logger.exception(e)
        abort(500)

@app.route('/admin/export')
def export_models():
    try:
        # Get all models
        models = get_models()
        
        # Create a string buffer to write CSV data
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Name', 'Model ID', 'Provider', 'Context Length', 'Max Output',
                        'Input Price', 'Output Price', 'Latency', 'Throughput', 'URL'])
        
        # Write data
        for model in models:
            for provider in model.get('providers', []):
                if provider in model.get('provider_details', {}):
                    details = model['provider_details'][provider]
                    writer.writerow([
                        model['name'],
                        model['model_id'],
                        provider,
                        details.get('context', ''),
                        details.get('max_output', ''),
                        details.get('input_price', ''),
                        details.get('output_price', ''),
                        details.get('latency', ''),
                        details.get('throughput', ''),
                        details.get('url', '')
                    ])
        
        # Move cursor to beginning of file
        output.seek(0)
        
        # Return the CSV file
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name='models.csv'
        )
    except Exception as e:
        logger.error(f"Error exporting models: {str(e)}")
        logger.exception(e)
        abort(500)

@app.route('/admin/refresh', methods=['POST'])
def refresh_models():
    try:
        # Start scraping in background
        logger.info("Starting model refresh...")
        if start_scraping():
            logger.info("Model refresh started successfully")
        else:
            logger.warning("Scraping already in progress")
        return redirect('/admin')
    except Exception as e:
        logger.error(f"Error starting model refresh: {str(e)}")
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