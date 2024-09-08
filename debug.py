import os
import json
import asyncio
import logging
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from langchain.prompts.prompt import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain_openai import RunnableSequence

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(filename='scraper_debug.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Function to initialize OpenAI API
def initialize_openai():
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        logging.error("OpenAI API key is not set in the environment variables.")
        raise ValueError("OpenAI API key is not set.")
    return ChatOpenAI(api_key=openai_api_key, temperature=0, model_name="gpt-4o-mini")

# Function to get all links from a webpage
async def get_all_links(page, url):
    await page.goto(url)
    content = await page.content()
    soup = BeautifulSoup(content, 'html.parser')
    links = set(a.get('href') for a in soup.find_all('a', href=True))
    logging.info(f"Found links: {links}")
    return links

# Function to call OpenAI API and get relevant links
async def get_relevant_links(openai_chain, urls):
    logging.info(f"Calling OpenAI API with URLs: {urls}")
    prompt = PromptTemplate(
        input_variables=["urls"],
        template=(
                "Given the following URLs, please determine if each one is relevant for scraping data to generate a company description. "
                "Mark each URL with 'YES' or 'NO'. Provide the result in JSON format with URLs as keys and 'YES' or 'NO' as values.\n\n"
                "URLs:\n{urls}\n\n"
                "Response format:\n"
                "{\n"
                "    'https://example.com/about': 'YES',\n"
                "    'https://example.com/contact': 'NO',\n"
                "    'https://example.com/products': 'YES'\n"
                "}\n\n"
                "Please format your response as shown above."
            )   
    )
    chain = prompt | openai_chain #TODO: here check the structure of answer maybe pydantic use
    response = await chain.invoke({"urls": urls})
    relevant_links = json.loads(response)
    logging.info(f"OpenAI response: {relevant_links}")
    return relevant_links

# Function to scrape data from relevant URLs
async def scrape_data_from_urls(page, relevant_urls):
    data = {}
    for url in relevant_urls:
        logging.info(f"Scraping data from URL: {url}")
        await page.goto(url)
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        data[url] = soup.get_text()
    logging.info(f"Scraped data: {data}")
    return data

# Function to call OpenAI API to generate a description
async def generate_description(openai_chain, scraped_data):
    logging.info(f"Calling OpenAI API to generate description with data: {scraped_data}")
    prompt = PromptTemplate(
        input_variables=["data"],
        template="Generate a company description based on the following data. If the data is insufficient, return a list of URLs to scrape more information. Data: {data}"
    )
    chain = prompt | openai_chain
    response = await chain.invoke({"data": json.dumps(scraped_data)})
    description = json.loads(response)
    logging.info(f"OpenAI response: {description}")
    return description

# Main function
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Example main link
        main_url = "https://centrum1.pl/"
        logging.info(f"Starting scraping process for main URL: {main_url}")

        # Initialize OpenAI API
        openai = initialize_openai()

        # Step 2: Get all links from the main page
        all_links = await get_all_links(page, main_url)

        # Step 3: Get relevant links
        relevant_links = await get_relevant_links(openai, list(all_links))

        # Filter URLs
        relevant_urls = [url for url, mark in relevant_links.items() if mark == 'YES']
        logging.info(f"Relevant URLs to scrape: {relevant_urls}")

        # Step 4: Scrape data from relevant URLs
        scraped_data = await scrape_data_from_urls(page, relevant_urls)

        # Step 5 & 6: Generate description
        description = await generate_description(openai, scraped_data)

        # Step 7: Print final description
        print(f"Final company description: {description}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
