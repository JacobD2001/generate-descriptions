import sys
from contextlib import redirect_stdout
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def filter_relevant_sections(text: str) -> bool:
    """
    Filter out irrelevant sections based on keywords. This function can be 
    enhanced to look for specific patterns, keywords, or section sizes.
    """
    # Keywords indicating relevant sections
    relevant_keywords = ['about', 'company', 'mission', 'vision', 'team', 'history', 'overview', 'services', 'contact']
    
    # Keywords indicating irrelevant sections
    irrelevant_keywords = ['blog', 'news', 'article', 'download', 'catalogue', 'publications']
    
    # Return True if any relevant keyword is found and no irrelevant keywords exist
    if any(keyword in text.lower() for keyword in relevant_keywords):
        return True
    if any(keyword in text.lower() for keyword in irrelevant_keywords):
        return False
    return False

def remove_redundant_content(content_list: list) -> list:
    """
    Removes repetitive or overly similar content from the list.
    """
    seen = set()
    reduced_content = []
    for content in content_list:
        # Check if content is new (not seen before)
        if content not in seen and len(content.split()) > 5:  # Only keep meaningful content
            reduced_content.append(content)
            seen.add(content)  # Mark content as seen
    return reduced_content

def limit_word_count(content: str, max_words: int = 500) -> str:
    """
    Truncate content to a maximum number of words to avoid sending too much data.
    """
    words = content.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]) + "..."
    return content

def scrape_website(url: str, log_file: str = "debug_log.txt", max_words: int = 500) -> str:
    with open(log_file, 'w', encoding='utf-8') as f:
        # Redirect all prints to the specified log file
        with redirect_stdout(f):
            with sync_playwright() as p:
                # Launch a headless browser
                browser = p.chromium.launch(headless=False)  # Set headless=False for debugging
                page = browser.new_page()

                # Visit the main website (homepage)
                print(f"Visiting main URL: {url}")
                page.goto(url)
                html_content = page.content()

                # Parse the homepage content using BeautifulSoup
                soup = BeautifulSoup(html_content, 'lxml')

                # Step 1: Find the navbar and collect all links from it
                avoid_keywords = ['publications', 'downloads', 'catalogues', 'blog', 'download']  # Keywords to avoid
                navbar_links = []
                for nav in soup.find_all(['nav', 'ul', 'menu']):
                    for link in nav.find_all('a', href=True):
                        full_link = link['href']
                        
                        # Ensure the link is complete (relative links need to be completed with the base URL)
                        if full_link.startswith('/'):
                            full_link = url.rstrip('/') + full_link
                        
                        # Skip links containing any avoid_keywords
                        if any(keyword in full_link.lower() for keyword in avoid_keywords):
                            print(f"Skipping link due to keyword match: {full_link}")
                            continue  # Skip this link if it contains any of the avoid keywords
                        
                        navbar_links.append(full_link)

                # Remove duplicate links
                navbar_links = list(set(navbar_links))
                print(f"Found {len(navbar_links)} navbar links to scrape:")
                
                # Log the links to be scraped
                for idx, link in enumerate(navbar_links, 1):
                    print(f"{idx}. {link}")

                # Step 2: Scrape content from each navbar link, one level deep
                relevant_content = []
                for link in navbar_links:
                    try:
                        print(f"\nScraping URL: {link}")
                        page.goto(link)
                        subpage_content = page.content()

                        # Parse the subpage content using BeautifulSoup
                        sub_soup = BeautifulSoup(subpage_content, 'lxml')

                        # Collect relevant headings and text content from the subpage
                        headings = [heading.get_text(strip=True) for heading in sub_soup.find_all(['h1', 'h2', 'h3'])]
                        relevant_content.extend(headings)

                        # Collect text from main divs or sections
                        page_content = []
                        for section in sub_soup.find_all(['div', 'section']):
                            # Exclude sections with irrelevant content by checking class or ID
                            section_class_or_id = section.get('class', [])
                            if isinstance(section.get('id'), str):
                                section_class_or_id += [section.get('id')]

                            # Skip sections with irrelevant keywords like blog, news, article, etc.
                            if any(keyword in str(section_class_or_id).lower() for keyword in ['blog', 'news', 'article', 'newsletter', 'publications']):
                                print(f"Skipping irrelevant section in URL: {link}")
                                continue

                            # Get the text from the section (if it's relevant and passes the filtering)
                            section_text = section.get_text(strip=True)
                            if len(section_text.split()) > 30 and filter_relevant_sections(section_text):
                                page_content.append(section_text)
                                relevant_content.append(section_text)

                        # Log the scraped content
                        print(f"\nScraped {len(headings)} headings and collected content from {link}.")
                        if page_content:
                            print(f"Content scraped from {link}:\n" + "\n".join(page_content))
                        else:
                            print(f"No significant content found on {link}.")

                    except Exception as e:
                        print(f"Error scraping {link}: {str(e)}")
                        continue

                # Close the browser
                browser.close()

                # Step 3: Reduce redundant content
                reduced_content = remove_redundant_content(relevant_content)

                # Join all the relevant content into a single string
                scraped_data = " ".join(reduced_content)
                print("\nFinished scraping all links.")
                
                # Truncate content to a manageable size
                truncated_scraped_data = limit_word_count(scraped_data, max_words)
                
                # Log the final scraped data to the file
                print("\nScraped Data:\n")
                print(truncated_scraped_data)  # This will print the final scraped data into the log file for debugging.

        return truncated_scraped_data


if __name__ == "__main__":
    # URL to scrape (replace this with the URL you want to scrape)
    url_to_scrape = "https://www.spetech.com.pl/"
    
    # Optional: You can specify the log file where all prints will be saved for debugging
    log_filename = "scraping_debug_log.txt"

    # Call the scraping function
    result = scrape_website(url_to_scrape, log_file=log_filename)

    # Print the result (for demonstration purposes, this print will not be logged)
    print("Scraping finished. Check the log file for detailed output.")
