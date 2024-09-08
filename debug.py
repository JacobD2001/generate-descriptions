import os
import json
import asyncio
import logging
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from langchain.prompts.prompt import PromptTemplate
from langchain_openai import ChatOpenAI
from urllib.parse import urljoin
from urllib.parse import urljoin
import re
import json
from output_parsers import relevant_links_parser

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(filename='scraper_debug.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# # Function to initialize OpenAI API
# def initialize_openai():
#     openai_api_key = os.getenv("OPENAI_API_KEY")
#     if not openai_api_key:
#         logging.error("OpenAI API key is not set in the environment variables.")
#         raise ValueError("OpenAI API key is not set.")
#     return ChatOpenAI(api_key=openai_api_key, temperature=0, model_name="gpt-4o-mini")

# Function to get all links from a webpage
#TODO : Maybe adjust it with natural language processing for some links
async def get_all_links(page, url):
    await page.goto(url)
    content = await page.content()
    soup = BeautifulSoup(content, 'html.parser')

    # Create an empty set to store the full URLs
    full_links = set()

    # Define regex patterns to exclude
    phone_pattern = re.compile(r'^[\+\d\-\(\)\s]+$')  # Matches strings that look like phone numbers
    email_pattern = re.compile(r'.+@.+\..+')  # Matches basic email-like strings
    keyword_pattern = re.compile(r'blog|publications', re.IGNORECASE)  # Matches specific keywords

    # Extract all href attributes from <a> tags
    for a in soup.find_all('a', href=True):
        href = a.get('href').strip()  # Remove leading/trailing spaces

        # Skip links based on the following criteria:
        # 1. Links starting with "mailto:" or "tel:"
        # 2. Links that match the phone number pattern (numbers, +, -, (), spaces)
        # 3. Links that look like email addresses but don't start with "mailto:"
        # 4. Links containing specific keywords like "blog" or "publications"
        if (
            href.startswith('mailto:') or
            href.startswith('tel:') or
            phone_pattern.match(href) or
            (email_pattern.match(href) and not href.startswith('mailto:')) or
            keyword_pattern.search(href)
        ):
            continue

        # Join the base URL with the href to create the full URL
        full_url = urljoin(url, href)

        # Add the full URL to the set
        full_links.add(full_url)

    logging.info(f"Filtered links: {full_links}")
    return full_links


# Function to call OpenAI API and get relevant links
# TODO: Adjust prompt 
async def get_relevant_links(urls):
    logging.info(f"Calling OpenAI API with URLs: {urls}")

    get_relevant_links_template = """
    Na podstawie podanych linków, oznacz te, pod którymi znajdują się istotne informacje do stworzenia opisu firmy.
    Opis firmy ma być krótki i zwięzły, zawierający takie informacje o firmie jak:
    - Co firma oferuje, czy sprzedaje produkty, czy usługi, czy jest dystrybutorem?
    - W jakiej branży działa firma?
    Zazwyczaj takie informacje powinny znajdywać się w zakładce typu o nas, kontakt lub w opisie produktów.
    Oznacz link 'YES' jeśli zawiera on informacje istotne, a 'NO' jeśli nie zawiera.
    Postaraj się nie zaznaczać więcej niż 3 linki jako 'YES'. Zależy nam na samych najważniejszych informacjach.
    Linki: {urls}
    W odpowiedzi nie pomijaj żadnego linku. 
    Liczba linków i linki powinny zgadzać się z podanymi. Dodaj jedynie oznaczenia 'YES' lub 'NO' dla każdego linku.
    \n{format_instructions}
    """
    
    # Define the prompt template
    get_relevant_links_prompt_template = PromptTemplate(
        input_variables=["urls"],
        template=get_relevant_links_template,
        partial_variables={
            "format_instructions": relevant_links_parser.get_format_instructions()
        },
    )
    
    # create the llm
    llm = ChatOpenAI(temperature=0, model_name="gpt-4o-mini")

    # Combine the prompt and the LLM chain
    chain = get_relevant_links_prompt_template | llm | relevant_links_parser

    res = chain.invoke(input={"urls": urls})

    # Log the openai response
    logging.info(f"OpenAI response: {res}")
    
    return res

# Function to scrape data from relevant URLs
# async def scrape_data_from_urls(page, relevant_urls):
#     data = {}
#     for url in relevant_urls:
#         logging.info(f"Scraping data from URL: {url}")
#         await page.goto(url)
#         content = await page.content()
#         soup = BeautifulSoup(content, 'html.parser')
#         data[url] = soup.get_text()
#     logging.info(f"Scraped data: {data}")
#     return data

# # Function to call OpenAI API to generate a description
# async def generate_description(openai_chain, scraped_data):
#     logging.info(f"Calling OpenAI API to generate description with data: {scraped_data}")
#     prompt = PromptTemplate(
#         input_variables=["data"],
#         template="Generate a company description based on the following data. If the data is insufficient, return a list of URLs to scrape more information. Data: {data}"
#     )
#     chain = prompt | openai_chain
#     response = await chain.invoke({"data": json.dumps(scraped_data)})
#     description = json.loads(response)
#     logging.info(f"OpenAI response: {description}")
#     return description

# Main function
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Example main link
        main_url = "https://centrum1.pl/"
        logging.info(f"Starting scraping process for main URL: {main_url}")

        # Initialize OpenAI API
        # openai = initialize_openai()

        # Step 2: Get all links from the main page
        all_links = await get_all_links(page, main_url)
        logging.info(f"Full links: {all_links}")

        # Step 3: Get relevant links
        relevant_links = await get_relevant_links(list(all_links))
        logging.info(f"Relevant links: {relevant_links}")

        # Filter URLs
        #relevant_urls = [url for url, mark in relevant_links.items() if mark == 'YES']
        # logging.info(f"Relevant URLs to scrape: {relevant_urls}")

        # Step 4: Scrape data from relevant URLs
        # scraped_data = await scrape_data_from_urls(page, relevant_urls)

        # Step 5 & 6: Generate description
        # description = await generate_description(openai, scraped_data)

        # Step 7: Print final description
        # print(f"Final company description: {description}")

        await browser.close()

if __name__ == "__main__":
    load_dotenv()
    print("Starting main function")

    asyncio.run(main())
