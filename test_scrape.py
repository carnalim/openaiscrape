from playwright.sync_api import sync_playwright, expect
import re
import time
import json

def get_model_urls(page):
    """Get all model URLs from the models page"""
    print("\nGetting model URLs from models page...")
    page.goto('https://openrouter.ai/models')
    time.sleep(5)  # Wait for dynamic content
    
    # Find all model links
    model_links = page.query_selector_all('a[href*="/"]')
    model_urls = []
    
    for link in model_links:
        href = link.get_attribute('href')
        if href and ('anthropic/' in href or 'google/' in href or 'meta/' in href or 'mistral/' in href):
            full_url = f"https://openrouter.ai{href}"
            if full_url not in model_urls:
                model_urls.append(full_url)
                print(f"Found model URL: {full_url}")
    
    return model_urls

def scrape_model_providers(url, page):
    """Scrape provider information for a specific model"""
    print(f"\nScraping {url}")
    
    # Navigate with longer timeout
    page.set_default_timeout(60000)  # 60 seconds
    page.goto(url)
    
    # Wait for content to load
    time.sleep(5)
    
    # Take screenshot
    model_name = url.split('/')[-1]
    screenshot_path = f"screenshots/{model_name}.png"
    page.screenshot(path=screenshot_path)
    print(f"\nSaved screenshot as {screenshot_path}")
    
    providers_data = []
    
    # Look for table rows containing provider information
    rows = page.query_selector_all('tr')
    if rows:
        current_provider = None
        provider_data = {}
        
        for row in rows:
            cells = row.query_selector_all('td')
            if cells and len(cells) > 1:
                # Get text content of cells
                cell_texts = [cell.inner_text().strip() for cell in cells]
                
                # Check if this is a provider row (usually has fewer columns)
                if len(cell_texts) <= 2 and any(provider in cell_texts[0].lower() for provider in ['anthropic', 'google', 'meta', 'mistral', 'openai']):
                    # If we have a previous provider's data, save it
                    if current_provider and provider_data:
                        providers_data.append({
                            "provider": current_provider,
                            "data": provider_data
                        })
                    
                    # Start new provider data
                    current_provider = cell_texts[0]
                    provider_data = {}
                else:
                    # Add data points to current provider
                    if len(cell_texts) >= 2:
                        key = cell_texts[0].strip()
                        value = cell_texts[1].strip()
                        if key and value:
                            provider_data[key] = value
        
        # Add the last provider's data
        if current_provider and provider_data:
            providers_data.append({
                "provider": current_provider,
                "data": provider_data
            })
    
    return {
        "model_url": url,
        "providers": providers_data
    }

def main():
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={'width': 1280, 'height': 720})
        page = context.new_page()
        
        try:
            # Get all model URLs
            model_urls = get_model_urls(page)
            
            # Create screenshots directory if it doesn't exist
            import os
            os.makedirs('screenshots', exist_ok=True)
            
            # Scrape each model's providers
            all_results = []
            for url in model_urls:
                result = scrape_model_providers(url, page)
                all_results.append(result)
                print(f"\nResults for {url}:")
                print(json.dumps(result, indent=2))
            
            # Save all results to a JSON file
            with open('model_providers.json', 'w') as f:
                json.dump(all_results, indent=2, fp=f)
            print("\nAll results saved to model_providers.json")
            
        except Exception as e:
            print(f"Error: {str(e)}")
        finally:
            browser.close()

if __name__ == '__main__':
    main()