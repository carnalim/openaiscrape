import requests
import sqlite3
import json
import logging
import re
import time
import concurrent.futures
from playwright.sync_api import sync_playwright

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect('models.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS models
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         name TEXT NOT NULL,
         slug TEXT NOT NULL UNIQUE,
         model_id TEXT,
         providers TEXT,
         provider_details TEXT,
         description TEXT,
         timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
    ''')
    c.execute('''CREATE TABLE IF NOT EXISTS rankings
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         category TEXT NOT NULL, 
         rank INTEGER NOT NULL,
         model_name TEXT NOT NULL,
         model_slug TEXT, 
         score REAL,
         timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
    ''')
    c.execute('''CREATE TABLE IF NOT EXISTS apps
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         app_name TEXT NOT NULL UNIQUE,
         app_url TEXT,
         token_count_raw TEXT, 
         token_count REAL,
         timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
    ''')
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

def scrape_provider_details(model_path):
    """Scrape provider details using Playwright"""
    # Using a single Playwright instance per function call for simplicity
    # In a larger app, consider managing the instance more globally
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 720})
        page = context.new_page()

        try:
            url = f"https://openrouter.ai/{model_path}"
            logger.info(f"Scraping providers from {url}")

            page.goto(url, timeout=60000) # Increased timeout
            time.sleep(5)  # Wait for content to load

            providers = []
            provider_details = {}

            # Find provider rows in table
            rows = page.query_selector_all('tr')
            current_provider = None
            current_details = {}

            for row in rows:
                cells = row.query_selector_all('td')
                if cells and len(cells) > 1:
                    cell_texts = [cell.inner_text().strip() for cell in cells]

                    # Check if this is a provider row - look for provider name in first cell
                    first_cell = cell_texts[0].lower()
                    # More robust check for provider names
                    provider_keywords = ['anthropic', 'google', 'meta', 'mistral', 'openai', 'cohere', 'perplexity', 'microsoft']
                    is_provider_row = any(keyword in first_cell for keyword in provider_keywords) and len(cell_texts) <= 3 # Provider rows often have fewer cells initially

                    if is_provider_row:
                        # Save previous provider details if exists
                        if current_provider and current_details:
                            providers.append(current_provider)
                            provider_details[current_provider] = current_details

                        # Start new provider
                        current_provider = cell_texts[0] # Use the exact text
                        current_details = {}

                        # Set provider URL based on first word of provider name
                        provider_base = current_provider.lower().split()[0].split('/')[0] # Handle cases like 'OpenAI (GPT-4)'
                        if provider_base == 'meta': provider_base = 'meta' # Specific case
                        elif provider_base == 'mistralai': provider_base = 'mistral'
                        # Add more specific mappings if needed
                        current_details['url'] = f'https://{provider_base}.ai' if provider_base not in ['openrouter', 'nousresearch'] else f'https://{provider_base}.com'


                        # If there's additional data in other cells, capture it
                        if len(cell_texts) > 1:
                            for i, text in enumerate(cell_texts[1:], 1):
                                if text.strip():  # Only add non-empty cells
                                    current_details[f'info_{i}'] = text.strip()
                    elif current_provider and len(cell_texts) >= 2:
                        # Add details to current provider
                        # --- Revised Detail Extraction Logic ---
                        # Try to find key-value pairs more flexibly within the row
                        possible_key_elements = row.query_selector_all('td:first-child, span[class*="label"], dt')
                        possible_value_elements = row.query_selector_all('td:nth-child(2), span[class*="value"], dd')

                        if possible_key_elements and possible_value_elements:
                            key_text = possible_key_elements[0].inner_text().lower().strip().replace(':', '')
                            value_text = possible_value_elements[0].inner_text().strip()

                            # Add more specific logging for debugging
                            # logger.debug(f"Found potential detail: Key='{key_text}', Value='{value_text}' for Provider='{current_provider}'")

                            if key_text and value_text and value_text != '-': # Only store non-empty key-value pairs, ignore placeholders
                                sanitized_key = key_text.replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '')

                                if 'context' in sanitized_key:
                                    current_details['context'] = value_text
                                elif 'max output' in sanitized_key or ('output' in sanitized_key and 'tokens' in sanitized_key and '$' not in value_text):
                                     # Distinguish max output tokens from output price
                                    current_details['max_output'] = value_text
                                elif 'input' in sanitized_key and '$' in value_text:
                                    current_details['input_price'] = value_text
                                elif 'output' in sanitized_key and '$' in value_text:
                                    current_details['output_price'] = value_text
                                elif 'latency' in sanitized_key:
                                    current_details['latency'] = value_text
                                elif 'throughput' in sanitized_key:
                                    current_details['throughput'] = value_text
                                else:
                                    # Store other relevant info, avoid overwriting core fields if key is ambiguous
                                    if sanitized_key not in ['context', 'max_output', 'input_price', 'output_price', 'latency', 'throughput']:
                                         current_details[sanitized_key] = value_text
                        # --- End Revised Detail Extraction ---

            # Add last provider
            if current_provider and current_details:
                providers.append(current_provider)
                provider_details[current_provider] = current_details

            return {
                'providers': providers,
                'provider_details': provider_details
            }

        except Exception as e:
            logger.error(f"Error scraping provider details for {model_path}: {str(e)}")
            return None
        finally:
            # Ensure browser is closed even if errors occur
            try:
                browser.close()
            except Exception as close_err:
                logger.error(f"Error closing browser: {close_err}")


def get_model_details(model_path, models_data):
    """Get detailed information for a model from OpenRouter API"""
    # Removed Playwright scraping attempt - Rely solely on API

    description = None
    model_api_data = None # Initialize model_api_data

    # Always try to get description and details from API if possible
    try:
        # Find the specific model entry in the pre-fetched models_data
        model_api_data = next((m for m in models_data.get('data', []) if m.get('id') == model_path), None)
        if model_api_data:
            description = model_api_data.get('description')
        else: # Fallback to direct API call if not found in bulk data
             api_url = f"https://openrouter.ai/api/v1/models/{model_path}"
             headers = {
                 # Consider making the bearer token configurable or an env variable
                 'Authorization': 'Bearer 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',
                 'HTTP-Referer': 'https://localhost:5000', # Adjust if needed
                 'Accept': 'application/json'
             }
             response = requests.get(api_url, headers=headers, timeout=10)
             if response.ok:
                 model_api_data = response.json()
                 description = model_api_data.get('description')
    except Exception as api_err:
        logger.warning(f"Could not fetch description via API for {model_path}: {api_err}")
        model_api_data = None # Ensure it's None if API fails

    # Generate default description if needed
    if not description:
        provider = model_path.split('/')[0].title()
        description = f"Advanced language model from {model_path.split('/')[0].title()} with strong performance across various tasks."

    # --- Start API Data Processing ---
    # This block now runs unconditionally as we rely solely on the API
    # logger.info(f"Processing API data for {model_path}") # Optional: Add logging

    # Fall back to API data or defaults
    # logger.warning(f"Relying on API/defaults for {model_path}.") # Adjusted log message
    main_provider = model_path.split('/')[0]
    providers = [main_provider.title()] # Use title case for provider name
    provider_details = {}

    if model_api_data: # Use API data if available
        context = model_api_data.get('context_length') # Get raw value or None
        max_output = model_api_data.get('max_output_tokens') # Get raw value or None
        pricing = model_api_data.get('pricing', {})
        input_price_per_mil = pricing.get('input') # Price per 1M tokens
        output_price_per_mil = pricing.get('output') # Price per 1M tokens
        # Note: API might not provide latency/throughput directly, check API docs if needed
        latency = model_api_data.get('latency') # Assuming API provides this, else None
        throughput = model_api_data.get('throughput') # Assuming API provides this, else None

        # Format values carefully, handling None
        context_str = f"{context // 1000}K" if context else 'N/A'
        max_output_str = f"{max_output // 1000}K" if max_output else 'N/A'
        # Convert price per 1M to per 1K, with robust type handling
        input_price_str = 'N/A'
        if input_price_per_mil is not None:
            try:
                input_price_str = f"${(float(input_price_per_mil) * 1000):.3f}/1K"
            except (ValueError, TypeError):
                logger.warning(f"Could not convert input price '{input_price_per_mil}' to float for {model_path}")
                input_price_str = str(input_price_per_mil) # Use raw value if conversion fails

        output_price_str = 'N/A'
        if output_price_per_mil is not None:
            try:
                output_price_str = f"${(float(output_price_per_mil) * 1000):.3f}/1K"
            except (ValueError, TypeError):
                logger.warning(f"Could not convert output price '{output_price_per_mil}' to float for {model_path}")
                output_price_str = str(output_price_per_mil) # Use raw value if conversion fails

        latency_str = 'N/A'
        if latency is not None:
            try:
                latency_str = f"{float(latency):.2f}s"
            except (ValueError, TypeError):
                 logger.warning(f"Could not convert latency '{latency}' to float for {model_path}")
                 latency_str = str(latency) # Use raw value

        throughput_str = 'N/A'
        if throughput is not None:
            try:
                throughput_str = f"{float(throughput):.2f} t/s"
            except (ValueError, TypeError):
                 logger.warning(f"Could not convert throughput '{throughput}' to float for {model_path}")
                 throughput_str = str(throughput) # Use raw value


        provider_details = {
            providers[0]: { # Assuming only one provider in API fallback
                'context': context_str,
                'max_output': max_output_str,
                'input_price': input_price_str,
                'output_price': output_price_str,
                'latency': latency_str, # Add if available from API
                'throughput': throughput_str, # Add if available from API
                'url': f'https://{main_provider}.ai' if main_provider not in ['openrouter', 'nousresearch', 'meta-llama'] else f'https://{main_provider}.com' # Adjust URL logic slightly
            }
        }
    else: # Use hardcoded defaults if API also failed
        logger.warning(f"API fallback failed for {model_path}, using N/A defaults.")
        provider_details = {
            providers[0]: {
                'context': 'N/A',
                'max_output': 'N/A',
                'input_price': 'N/A',
                'output_price': 'N/A',
                'latency': 'N/A',
                'throughput': 'N/A',
                'url': f'https://{main_provider}.ai' if main_provider not in ['openrouter', 'nousresearch', 'meta-llama'] else f'https://{main_provider}.com'
            }
        }

    return {
        'providers': providers, # Should be just [main_provider.title()] in fallback
        'provider_details': provider_details,
        'description': description
    }


def get_all_models():
    """Get all models from OpenRouter.ai API"""
    api_url = "https://openrouter.ai/api/v1/models"
    headers = {
        'Authorization': 'Bearer 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',
        'HTTP-Referer': 'https://localhost:5000',
        'Accept': 'application/json'
    }

    try:
        response = requests.get(api_url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        models = []
        for model in data.get('data', []):
            model_id = model.get('id', '')
            # Filter out models without '/' and potentially other unwanted ones
            if '/' in model_id and ':' not in model_id: # Exclude tagged models like ':free' initially
                models.append(model_id)

        logger.info(f"Found {len(models)} models via API")
        return models, data # Return full data for description lookup
    except Exception as e:
        logger.error(f"Error getting models from API: {str(e)}")
        return [], None

def process_model(model_path, models_data):
    """Process a single model: get details and store in DB"""
    try:
        logger.info(f"Processing model: {model_path}")
        name_part = model_path.split('/')[-1]
        # Improved naming convention
        name = ' '.join(word.capitalize() for word in name_part.replace('-', ' ').split())

        details = get_model_details(model_path, models_data)

        if details:
            model_data = {
                "name": name,
                "slug": name_part, # Use the last part as slug
                "model_id": model_path,
                "providers": details['providers'],
                "provider_details": details['provider_details'],
                "description": details['description']
            }

            # Store model in database immediately
            conn = sqlite3.connect('models.db')
            c = conn.cursor()

            try:
                c.execute('''
                    INSERT OR REPLACE INTO models
                    (name, slug, model_id, providers, provider_details, description)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    model_data['name'],
                    model_data['slug'],
                    model_data['model_id'],
                    json.dumps(model_data['providers']),
                    json.dumps(model_data['provider_details']),
                    model_data['description']
                ))
                conn.commit()
            except Exception as e:
                logger.error(f"Error storing model {model_path} in database: {str(e)}")
                conn.rollback() # Rollback on error
            finally:
                conn.close()

            return model_data # Return data even if DB store failed? Or None?
    except Exception as e:
        logger.error(f"Error processing model {model_path}: {str(e)}")
    return None

# --- Start of NEW functions ---
def scrape_rankings(category='general', view='week'):
    """Scrape model rankings for a specific category and view."""
    ranking_data = []
    url = f"https://openrouter.ai/rankings/{category}?view={view}" if category != 'general' else f"https://openrouter.ai/rankings?view={view}"
    logger.info(f"Scraping rankings from {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 1024})
        page = context.new_page()

        try:
            page.goto(url, timeout=60000)
            time.sleep(5) # Wait for dynamic content

            # Find ranking rows - More robust selector targeting rows with rank-like text
            # This looks for table rows, or list items if the structure changed
            row_selectors = [
                'table tbody tr', # Standard table rows
                'div[role="listitem"]', # Common pattern for list-based layouts
                'li[class*="rank"]' # List items with 'rank' in class
            ]
            rows = []
            for selector in row_selectors:
                rows = page.query_selector_all(selector)
                if rows:
                    logger.info(f"Using selector '{selector}' for ranking rows.")
                    break # Use the first selector that finds elements

            logger.info(f"Found {len(rows)} potential ranking rows for {category}.")

            for i, row in enumerate(rows):
                # Skip header row if present (heuristic: check for th or header-like role/class)
                if row.query_selector('th') or row.get_attribute('role') == 'rowheader' or 'header' in (row.get_attribute('class') or ''):
                    continue
                try:
                    # Extract data - Try multiple selectors for each piece of data
                    rank_element = row.query_selector('td:nth-child(1), span[class*="rank"], div[class*="rank"]')
                    model_link_element = row.query_selector('td:nth-child(2) a, div[class*="name"] a, span[class*="model"] a')
                    score_element = row.query_selector('td:nth-child(3), div[class*="score"], span[class*="score"]') # Assuming score is 3rd column or has 'score' class

                    if rank_element and model_link_element: # Score is optional sometimes
                        rank_text = rank_element.inner_text().strip().replace('#', '')
                        model_name = model_link_element.inner_text().strip()
                        model_href = model_link_element.get_attribute('href')
                        score_text = score_element.inner_text().strip()

                        model_slug = None
                        if model_href and '/' in model_href:
                            # Extract slug like 'meta-llama/llama-3-sonar-large-32k-online'
                            parts = model_href.split('/')
                            # Ensure we get the last two parts correctly, even with leading/trailing slashes
                            valid_parts = [p for p in parts if p]
                            if len(valid_parts) >= 2:
                                model_slug = f"{valid_parts[-2]}/{valid_parts[-1]}"
                                # Handle potential query params in slug
                                model_slug = model_slug.split('?')[0]

                        try:
                            rank = int(rank_text)
                        except ValueError:
                            logger.warning(f"Could not parse rank '{rank_text}' for {model_name} in {category}")
                            rank = i + 1 # Use row index as fallback rank

                        try:
                            # Handle potential non-numeric scores like '-'
                            score = float(score_text) if score_text and score_text != '-' else None
                        except ValueError:
                             logger.warning(f"Could not parse score '{score_text}' for {model_name} in {category}")
                             score = None

                        ranking_data.append({
                            'category': category,
                            'rank': rank,
                            'model_name': model_name,
                            'model_slug': model_slug,
                            'score': score
                        })
                        # logger.info(f"Scraped Rank {rank}: {model_name} (Slug: {model_slug}), Score: {score}")
                    else:
                        # Avoid logging warnings for header rows or empty rows
                        if row.inner_text().strip(): # Log only if row has content
                             logger.warning(f"Could not extract all required elements from row {i+1} for {category}. Check selectors.")
                             # logger.debug(f"Row HTML: {row.inner_html()}") # Optional: debug row content

                except Exception as e:
                    logger.error(f"Error processing ranking row {i+1} for {category}: {str(e)}")
                    # logger.debug(f"Row HTML: {row.inner_html()}") # Log row HTML for debugging

        except Exception as e:
            logger.error(f"Error scraping rankings page {url}: {str(e)}")
        finally:
            try:
                browser.close()
            except Exception as close_err:
                logger.error(f"Error closing browser for rankings: {close_err}")


    logger.info(f"Finished scraping {len(ranking_data)} rankings for {category}.")
    return ranking_data


def store_ranking_data(ranking_data):
    """Store scraped ranking data into the database."""
    if not ranking_data:
        return

    conn = sqlite3.connect('models.db')
    c = conn.cursor()

    # Clear old rankings for the specific categories being updated
    categories = list(set(item['category'] for item in ranking_data))
    placeholders = ','.join('?' * len(categories))
    try:
        c.execute(f'DELETE FROM rankings WHERE category IN ({placeholders})', categories)
        logger.info(f"Cleared old rankings for categories: {categories}")
    except Exception as e:
        logger.error(f"Error clearing old rankings: {str(e)}")
        conn.close()
        return # Stop if clearing fails

    try:
        insert_count = 0
        for item in ranking_data:
            # Ensure model_slug is not None before inserting, or handle NULL in DB schema
            if item.get('model_slug'):
                c.execute('''
                    INSERT INTO rankings (category, rank, model_name, model_slug, score)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    item['category'],
                    item['rank'],
                    item['model_name'],
                    item['model_slug'],
                    item['score']
                ))
                insert_count += 1
            else:
                logger.warning(f"Skipping ranking insert for {item['model_name']} due to missing slug.")

        conn.commit()
        logger.info(f"Successfully stored {insert_count} rankings for categories: {categories}.")
    except Exception as e:
        logger.error(f"Error storing ranking data: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

def scrape_apps():
    """Scrape app showcase data from the OpenRouter homepage."""
    app_data = []
    url = "https://openrouter.ai/"
    logger.info(f"Scraping app showcase from {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 1024})
        page = context.new_page()

        try:
            page.goto(url, timeout=60000)
            time.sleep(5) # Wait for dynamic content

            # Find app showcase items - adjust selector based on inspection
            # Example: Look for links within a specific section/container
            app_container_selector = '#apps, .app-showcase, section[aria-labelledby*="apps"]' # Try multiple common patterns
            app_link_selector = f'{app_container_selector} a[href*="/"]' # Links within the container
            app_elements = page.query_selector_all(app_link_selector)

            # Fallback: Look for article elements with links inside
            if not app_elements:
                 app_elements = page.query_selector_all('article a[href*="/"]')

            logger.info(f"Found {len(app_elements)} potential app link elements.")

            processed_apps = set() # Avoid duplicates if multiple links point to same app
            for element in app_elements:
                app_url = element.get_attribute('href')
                 # Ensure URL is absolute
                if app_url.startswith('/'):
                    app_url = f"https://openrouter.ai{app_url}"
                
                if app_url in processed_apps:
                    continue # Skip already processed app URL

                try:
                    app_name = element.query_selector('h3, div[class*="title"]').inner_text().strip() # Example
                    app_url = element.get_attribute('href')
                    # Token count might be in a sibling or child element
                    token_element = element.query_selector('div[class*="token"], span[class*="count"]') # Example
                    token_count_raw = token_element.inner_text().strip() if token_element else None

                    token_count = None
                    if token_count_raw:
                        # Extract numeric value (e.g., "41.3b tokens" -> 41.3e9)
                        match = re.search(r'([\d.]+)([kmb])?', token_count_raw.lower())
                        if match:
                            value = float(match.group(1))
                            multiplier = match.group(2)
                            if multiplier == 'k':
                                token_count = value * 1e3
                            elif multiplier == 'm':
                                token_count = value * 1e6
                            elif multiplier == 'b':
                                token_count = value * 1e9
                            else:
                                token_count = value

                    if app_name and app_url:
                         # Ensure URL is absolute
                        if app_url.startswith('/'):
                            app_url = f"https://openrouter.ai{app_url}"

                        app_data.append({
                            'app_name': app_name,
                            'app_url': app_url,
                            'token_count_raw': token_count_raw,
                            'token_count': token_count
                        })
                        # logger.info(f"Scraped App: {app_name}, Tokens: {token_count_raw}")
                    else:
                         logger.warning("Could not extract app name or URL from element.")
                         # logger.debug(f"App Element HTML: {element.inner_html()}")

                except Exception as e:
                    logger.error(f"Error processing app element: {str(e)}")
                    # logger.debug(f"App Element HTML: {element.inner_html()}")

        except Exception as e:
            logger.error(f"Error scraping app showcase page {url}: {str(e)}")
        finally:
            try:
                browser.close()
            except Exception as close_err:
                 logger.error(f"Error closing browser for apps: {close_err}")

    logger.info(f"Finished scraping {len(app_data)} apps.")
    return app_data

def store_app_data(app_data):
    """Store scraped app data into the database."""
    if not app_data:
        return

    conn = sqlite3.connect('models.db')
    c = conn.cursor()

    # Optional: Clear old app data before inserting new ones
    # c.execute('DELETE FROM apps')

    try:
        for item in app_data:
            c.execute('''
                INSERT OR REPLACE INTO apps (app_name, app_url, token_count_raw, token_count)
                VALUES (?, ?, ?, ?)
            ''', (
                item['app_name'],
                item['app_url'],
                item['token_count_raw'],
                item['token_count']
            ))
        conn.commit()
        logger.info(f"Successfully stored/updated {len(app_data)} apps.")
    except Exception as e:
        logger.error(f"Error storing app data: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

# --- End of NEW functions ---

def scrape_models(should_stop=None):
    """Scrape all models with concurrent processing"""
    model_paths, models_data = get_all_models()
    if not models_data:
        logger.error("Failed to get model list from API. Aborting model scrape.")
        return []

    logger.info(f"Starting scrape for {len(model_paths)} models...")

    models = []
    # Use ThreadPoolExecutor for I/O bound tasks like scraping
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor: # Increased max_workers to 10
        # Pass models_data to each worker
        future_to_model = {executor.submit(process_model, path, models_data): path for path in model_paths}
        for i, future in enumerate(concurrent.futures.as_completed(future_to_model)):
            if should_stop and should_stop():
                logger.info("Stopping model scraping as requested")
                # Attempt to cancel pending futures (may not always work)
                for f in future_to_model:
                    f.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                break

            model_path = future_to_model[future]
            try:
                model = future.result()
                if model:
                    models.append(model)
                logger.info(f"Completed model {i+1}/{len(model_paths)}: {model_path}")
            except Exception as exc:
                logger.error(f'{model_path} generated an exception: {exc}')

    if not (should_stop and should_stop()):
        logger.info(f"Finished scraping models. Successfully processed {len(models)} models.")
    return models

def get_models():
    """Retrieve all models from the database"""
    try:
        conn = sqlite3.connect('models.db')
        # Return rows as dictionaries
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('''
            SELECT name, slug, model_id, providers, provider_details, description
            FROM models ORDER BY name
        ''')
        # Convert Row objects to dictionaries and parse JSON fields
        models_list = []
        for row in c.fetchall():
            model_dict = dict(row)
            try:
                model_dict['providers'] = json.loads(model_dict['providers']) if model_dict['providers'] else []
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Could not parse providers JSON for {model_dict['slug']}")
                model_dict['providers'] = [] # Default to empty list on error

            try:
                model_dict['provider_details'] = json.loads(model_dict['provider_details']) if model_dict['provider_details'] else {}
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Could not parse provider_details JSON for {model_dict['slug']}")
                model_dict['provider_details'] = {} # Default to empty dict on error

            models_list.append(model_dict)

        conn.close()
        return models_list
    except Exception as e:
        logger.error(f"Error getting models from database: {str(e)}")
        return []

def get_model_by_slug(slug):
    """Retrieve a single model by its slug from the database"""
    try:
        conn = sqlite3.connect('models.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('''
            SELECT name, slug, model_id, providers, provider_details, description
            FROM models WHERE slug = ?
        ''', (slug,))
        row = c.fetchone()
        conn.close()
        if row:
            model_dict = dict(row)
            try:
                model_dict['providers'] = json.loads(model_dict['providers']) if model_dict['providers'] else []
            except (json.JSONDecodeError, TypeError):
                 logger.warning(f"Could not parse providers JSON for {model_dict['slug']}")
                 model_dict['providers'] = []
            try:
                model_dict['provider_details'] = json.loads(model_dict['provider_details']) if model_dict['provider_details'] else {}
            except (json.JSONDecodeError, TypeError):
                 logger.warning(f"Could not parse provider_details JSON for {model_dict['slug']}")
                 model_dict['provider_details'] = {}
            return model_dict
        return None
    except Exception as e:
        logger.error(f"Error getting model by slug '{slug}': {str(e)}")
        return None

# --- Add functions to retrieve ranking and app data ---
def get_rankings_by_category(category):
    """Retrieve rankings for a specific category from the database"""
    try:
        conn = sqlite3.connect('models.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('''
            SELECT rank, model_name, model_slug, score
            FROM rankings WHERE category = ? ORDER BY rank
        ''', (category,))
        rankings = [dict(row) for row in c.fetchall()]
        conn.close()
        return rankings
    except Exception as e:
        logger.error(f"Error getting rankings for category '{category}': {str(e)}")
        return []

def get_all_apps():
    """Retrieve all apps from the database"""
    try:
        conn = sqlite3.connect('models.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('''
            SELECT app_name, app_url, token_count_raw, token_count
            FROM apps ORDER BY token_count DESC
        ''')
        apps = [dict(row) for row in c.fetchall()]
        conn.close()
        return apps
    except Exception as e:
        logger.error(f"Error getting apps from database: {str(e)}")
        return []
# --- End of new retrieval functions ---


if __name__ == '__main__':
    init_db()
    # Scrape models first
    scrape_models()

    # Then scrape rankings for different categories
    categories_to_scrape = ['general', 'roleplay', 'programming']
    for category in categories_to_scrape:
        rankings = scrape_rankings(category=category, view='week') # Or 'day', 'month'
        store_ranking_data(rankings)

    # Finally, scrape apps
    apps = scrape_apps()
    store_app_data(apps)

    logger.info("Initial scraping complete.")