from dotenv import load_dotenv
import os
from typing import Tuple
from langchain.prompts.prompt import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain.chains import LLMChain
from langchain.schema import HumanMessage
import functions_framework
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Load the environment variables from .env
load_dotenv()

# Retrieve the OpenAI API key from the .env file
openai_api_key = os.getenv('OPENAI_API_KEY')


# Function to scrape the website using Playwright and BeautifulSoup
def scrape_website(url: str) -> str:
    with sync_playwright() as p:
        # Launch a headless browser (since we are in the cloud, use headless=True)
        browser = p.chromium.launch(headless=True)
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

                    # Get the text from the section (if it's relevant)
                    section_text = section.get_text(strip=True)
                    if len(section_text.split()) > 30:  # Only consider sections with more than 30 words
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

        # Join all the relevant content into a single string
        scraped_data = " ".join(relevant_content)
        print("\nFinished scraping all links.")

        return scraped_data



# Function to generate a company description using LangChain's OpenAI ChatGPT
def generate_company_description(scraped_data: str) -> str:
    # Create a prompt template for company description generation
    description_template = """
    Based on the following scraped information from a company's website: {scraped_info},
    please generate:
    1. A concise company description that includes their products and services.
    2. Key details about the company, such as their industry and main focus.

    Use the provided information and format it clearly.
    """

    # Prepare the prompt template with the scraped information
    description_prompt_template = PromptTemplate(
        input_variables=["scraped_info"],
        template=description_template,
    )

    # Create the OpenAI Chat Model (using GPT-4 or GPT-3.5-turbo)
    llm = ChatOpenAI(temperature=0, model_name="gpt-4o-mini", openai_api_key=openai_api_key)

    # Create the LLMChain with the prompt and the model
    chain = LLMChain(
        llm=llm,
        prompt=description_prompt_template
    )

    # Invoke the chain to generate the description
    response = chain.run(scraped_info=scraped_data)

    return response


@functions_framework.http
def hello_http(request):
    """HTTP Cloud Function to scrape a website, verify REGON, and generate a description."""
    # Parse the JSON payload from the request
    request_json = request.get_json(silent=True)

    if request_json:
        # Extract 'row', 'strona_www', and 'regon' from the payload
        row = request_json.get('row', 'No row provided')
        strona_www = request_json.get('strona_www', 'No URL provided')
        regon = request_json.get('regon', 'No REGON provided')

        # Log the received values (for testing and debugging)
        print(f"Received data - Row: {row}, Strona WWW: {strona_www}, REGON: {regon}")

        # Scrape the website
        scraped_data = scrape_website(strona_www)
        print(f"Scraped Data: {scraped_data}")

        # Verify if the REGON is present in the scraped data
        if regon in scraped_data:
            verification_status = "Zweryfikowano"
        else:
            verification_status = "Potrzebna weryfikacja"

        # Step 5: Generate the description using GPT based on the scraped data
        description = generate_company_description(scraped_data)
        print(f"Generated Description: {description}")

        # Return the verification status and generated description (will update Google Sheet later)
        return {
            'row': row,
            'verification_status': verification_status,
            'scraped_data': scraped_data,  # Truncate long data for brevity
            'description': description
        }, 200
    else:
        return "Invalid request", 400


if __name__ == "__main__":
    load_dotenv()
