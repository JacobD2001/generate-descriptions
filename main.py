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
        # Launch a headless browser
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Visit the website
        page.goto(url)

        # Extract page content
        html_content = page.content()

        # Close the browser
        browser.close()

        # Parse the page content using BeautifulSoup
        soup = BeautifulSoup(html_content, 'lxml')

        # Define a set of keywords or tags to exclude from scraping (e.g., blogs, newsletters, articles)
        exclude_keywords = ['blog', 'news', 'article', 'newsletter']

        # Step 1: Collect the main headings and text content from the page
        relevant_content = []

        # Get headings (h1, h2, h3) to understand the high-level structure
        for heading in soup.find_all(['h1', 'h2', 'h3']):
            relevant_content.append(heading.get_text(strip=True))

        # Step 2: Collect text from main divs, skipping blogs or irrelevant sections
        for div in soup.find_all('div'):
            # Ensure class and id are handled as lists
            div_class_or_id = div.get('class', [])
            if isinstance(div.get('id'), str):
                div_class_or_id += [div.get('id')]

            # Skip divs that have irrelevant classes or IDs
            if any(keyword in str(div_class_or_id).lower() for keyword in exclude_keywords):
                continue  # Skip if the div is likely part of a blog or irrelevant section

            # Get the text inside the div (limit depth, avoid deep product details)
            relevant_text = div.get_text(strip=True)
            if len(relevant_text.split()) > 30:  # Consider divs with more than 30 words as relevant sections
                relevant_content.append(relevant_text)

        # Join all the relevant content into a single string
        scraped_data = " ".join(relevant_content)

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
            'scraped_data': scraped_data[:1000],  # Truncate long data for brevity
            'description': description
        }, 200
    else:
        return "Invalid request", 400


if __name__ == "__main__":
    load_dotenv()
