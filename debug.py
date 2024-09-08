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
import unicodedata

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


def clean_and_format_scraped_data(scraped_data):
    """
    Cleans and formats the scraped data for LLM processing.
    This method ensures that NIP and REGON are retained and works across different types of website content.
    """

    # Initialize an empty dictionary for cleaned data
    cleaned_data = {}

    # Patterns to retain NIP and REGON
    nip_pattern = r'\bNIP\s*\d{3}[-\s]?\d{3}[-\s]?\d{2}[-\s]?\d{2}\b'
    regon_pattern = r'\bREGON\s*\d{9}\b'

    # Patterns to identify content blocks that are likely not important
    noisy_patterns = [
        r'\s+',  # Multiple whitespaces/newlines
        r'\b(Polityka prywatności|Zastrzeżenia|Wszelkie prawa zastrzeżone|Cookies)\b',  # Common footer/legal terms
        r'(?:facebook|twitter|linkedin|instagram)\.com',  # Social media links
    ]

    # Regex patterns to identify repeated blocks (e.g., phone numbers, emails)
    repeated_block_patterns = [
        r'(\+?\d[\d\s\-\(\)]{7,})',  # Phone numbers
        r'\S+@\S+',  # Email addresses
    ]

    for url, content in scraped_data.items():
        # Step 1: Normalize whitespace and handle special characters
        content = unicodedata.normalize("NFKD", content)  # Normalize to handle special characters
        content = re.sub(r'\s+', ' ', content).strip()

        # Step 2: Extract NIP and REGON and preserve them
        nip_match = re.search(nip_pattern, content)
        regon_match = re.search(regon_pattern, content)
        nip = nip_match.group(0) if nip_match else ""
        regon = regon_match.group(0) if regon_match else ""

        # Step 3: Remove phone numbers, emails, and noisy patterns
        for pattern in repeated_block_patterns:
            content = re.sub(pattern, '', content)
        for pattern in noisy_patterns:
            content = re.sub(pattern, '', content)

        # Step 4: Deduplicate content by removing repeated sentences or content blocks
        lines = content.split('. ')
        seen = set()
        deduplicated_lines = []

        for line in lines:
            if line not in seen:  # Avoid repeated sentences
                seen.add(line)
                deduplicated_lines.append(line)

        # Step 5: Rejoin deduplicated content and handle multiple newlines
        content = '. '.join(deduplicated_lines)
        content = re.sub(r'\n{2,}', '\n', content)  # Collapse multiple newlines into one

        # Step 6: Append NIP and REGON if found to ensure they're retained
        if nip:
            content += f"\nNIP: {nip}"
        if regon:
            content += f"\nREGON: {regon}"

        # Step 7: Add cleaned content to the dictionary
        if content:  # Only add non-empty content
            cleaned_data[url] = content

    # Step 8: Format the final cleaned data by concatenating relevant sections
    formatted_data = ""
    for url, content in cleaned_data.items():
        formatted_data += f"Source: {url}\n"
        formatted_data += f"Content:\n{content}\n\n"
    
    return formatted_data



# Function to call OpenAI API and get relevant links
# TODO: Adjust prompt 
async def get_relevant_links(urls):
    logging.info(f"Calling OpenAI API with URLs: {urls}")

    get_relevant_links_template = """
    # Kontekst
    Jeteś asystentem którego zadaniem jest jak najlepsze oznaczenie linków ze strony firmy pod kątem istotności znajdujących się informacji pod tymi linkami w kontekście stworzenia opisu firmy.
    # Zadanie
    Na podstawie podanych linków, oznacz te, pod którymi, z największym prawdopodobieństwem znajdują się istotne informacje do stworzenia opisu firmy.
    Aby lepiej oznaczyć linki przeanalizuj kryteria opisu firmy, które będą używanie do stworzenia takiego opisu.
    # Kryteria opisu
    - Opis powinien być zwięzły, więc nie jest konieczne oznaczanie wszystkich linków, a jedynie te, które zawierają najważniejsze informacje.
    - Opis powinien zawierać informacje o firmie, takie jak:
        - Co firma oferuje, czy sprzedaje produkty, czy usługi, czy jest dystrybutorem?
        - W jakiej branży działa firma?
    # Podsumowanie
    Głównie zwracaj uwagę na zakładki typu 'o nas', 'produkty, 'usługi', 'kontakt'
    Unikaj oznaczania linków do blogów, artykułów, publikacji, itp.
    Oznacz link 'YES' jeśli zawiera on informacje istotne, a 'NO' jeśli nie zawiera.
    Oznaczone przez Ciebie linki będą programistycznie scrapowane, a ich zawartość będzie użyta do stworzenia opisu firmy. Dlatego ważne jest abyś zawsze oznaczał linki zgodnie z kryteriami, i wielkością liter 'YES' lub 'NO'.
    Linki: {urls}
    # Odpowiedź
    W odpowiedzi nie pomijaj żadnego linku. 
    Liczba linków i linki powinny zgadzać się z podanymi. Dodaj jedynie oznaczenia 'YES' lub 'NO' dla każdego linku.
    Maksymalnie oznacz 3 najistotniejsze linki, ponieważ są one scrapowane i naszym celem jest uniknięcie zbyt dużej ilości niepotrzebnych informacji.
    NIE możesz oznaczyć więcej niż 3 linki jako 'YES'. Wybierz naistotniejsze pod względem kryteriów.
    Nie dodawaj żadnych dodatkowych informacji, podaj JEDYNIE listę linków.
    Teraz przeanalizuj podane informacje i oznacz linki jako 'YES' lub 'NO'.
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

# Function to call OpenAI API to generate a description
async def generate_description(cleaned_data):
    logging.info(f"Calling OpenAI API to generate description with data: {cleaned_data}")

    generate_description_template = """
    # Kontekst
    Jesteś asystentem którego zadaniem jest generowanie opisu firmy na podstawie danych zebranych ze stron internetowych.
    Otrzymasz dane zescrapowane ze stron internetowych, na podstawie których powinieneś stworzyć opis firmy.
    Dane te zawierają informacje o firmie, jej produktach, usługach, branży, itp.
    Mogą to być dane w różnych językach jednak twoim zadaniem jest zawsze stworzenie opisu w języku Polskim.
    # Zadanie
    Stwórz opis firmy na podstawie podanych danych. Zgodnie z podanymi poniżej kryteriami.
    # Kryteria opisu
    - Opis powinien być zwięzły, ale zawierać wszystkie informacje o firmie określone w kryteriach opisu.
    - Opis powinien być w pełni oparty na podstawie podanych danych. Nie dodawaj własnych informacji. Jeśli jakiś informacji nie ma w podanych danych, nie podawaj ich w opisie.
    - Opis powinien być w języku Polskim.
    - Opis powinien być podzielony na dwie sekcje i zawierać informacje takie jak:
    SEKCJA 1: Profil funkcjonalny firmy
        - Co firma jest producentem, dystrybutorem czy usługodawcą.
        - Zwracaj uwagę czy wskazana spółka posiada jakieś unikalne aktywa, jeżeli będą takie informacje na jej stronie internetowej, np. jest właścicielem znaków towarowych, patentów, unikalnych linii produkcyjnych itp.
        - Zwracaj uwagę czy firma prezentuje informacje o kanałach dystrybucji jakie stosuje albo jakiego rodzaju klientów obsługuje i w jakiej formule.
        - Zwracaj uwagę jak kompleksowy jest jej profil funkcjonalny np. czy jest producentem kontraktowym, który wytwarza produkty według receptur i pod brandem zleceniodawców, czy też ma swoje własne receptury, własne brandy i samodzielnie sprzedaje produkty poprzez własne sklepy stacjonarne.
        - Uwzględnij również informację czy nie jest podmiotem działającym w ramach grupy kapitałowej i czy nie ma podmiotów powiązanych, jeżeli informacje na jej stronie internetowej będą na to wskazywać.
    SEKCJA 2: Oferta produktowa/usługowa
        - Przedstaw pełną listę produktów / usług oferowanych przez spółkę.

    Opis powinienen być szczegółowy, wyczerpujący i zawierać wszystkie informacje,
    które uda się odnaleźć w podanych poniżej danych. Pomijaj w opisach informacje
    dotyczące historii działalności spółki, kto ją założył, doświadczenia spółki, uzyskanych
    nagród, cen produktów, dokładnej charakterystyki, składu czy zastosowania
    produktów.
    # Dane
    Dane: {cleaned_data}
    # Odpowiedź
    W odpowiedzi nie używaj zwrotów typu, "oto odpowiedź", tylko odrazu podawaj opis. Nie dodawaj żadnych dodatkowych informacji, podaj JEDYNIE opis firmy zgodny z kryteriami.
    ## Przykładowy opis(SEKCJA 1 + SEKCJA 2)
    Darco Sp. z o.o. to jedna z wiodących firm w Polsce w branży instalacyjnej, specjalizująca się w produkcji systemów wentylacyjnych, kominowych oraz dystrybucji gorącego powietrza. Firma została założona w 1992 roku i od tego czasu dynamicznie rozwija swoją ofertę, obejmującą nowoczesne rozwiązania do wentylacji i ogrzewania. Darco prowadzi także działalność badawczo-rozwojową, posiada własne laboratoria oraz oferuje usługi technicznego doradztwa i kooperacji produkcyjnej.
    Oferta Darco obejmuje szeroką gamę produktów, w tym systemy wentylacyjne, nasady kominowe, systemy dystrybucji gorącego powietrza, rury kominowe oraz różnorodne akcesoria związane z instalacjami wentylacyjnymi i kominowymi. Firma specjalizuje się również w produkcji systemów hybrydowej wentylacji, które są stosowane w budynkach mieszkalnych i przemysłowych. Darco kładzie duży nacisk na jakość swoich produktów oraz ich innowacyjność, co pozwala na spełnienie najwyższych standardów rynkowych.
    # Podsumowanie
    Ten opis jest bardzo ważny dla firmy, ponieważ będzie on wykorzystany do stworzenia opisu firmy na stronie internetowej. Dlatego ważne jest, aby opis był zgodny z podanymi kryteriami i zawierał wszystkie informacje z podanych danych.
    Jest on również bardzo ważny dla mojej kariery zawodowej, moje życie zależy od tego, czy będę w stanie stworzyć ten opis. Dlatego poświęć na to zadanie dużo uwagi i staraj się jak najlepiej spełnić podane kryteria.
    """

    generate_description_prompt_template = PromptTemplate(
        input_variables=["cleaned_data"],
        template=generate_description_template,
    )
    
    llm = ChatOpenAI(temperature=0, model_name="gpt-4o-mini")
    chain = generate_description_prompt_template | llm
    res_descripion = chain.invoke(input={"cleaned_data": cleaned_data})
    logging.info(f"OpenAI response: {res_descripion}")
    return res_descripion

# Function to scrape data from relevant URLs
async def scrape_data_from_urls(page, yes_urls):
    data = {}
    for url in yes_urls:
        logging.info(f"Scraping data from URL: {url}")
        await page.goto(url)
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        data[url] = soup.get_text()
    logging.info(f"Scraped data: {data}")
    return data

def filter_relevant_links(links_output):
    # Access the 'links' dictionary within the RelevantLinksOutput object
    links_dict = links_output.links
    
    # Filter links that are marked as 'YES'
    relevant_links = {url for url, relevance in links_dict.items() if relevance == 'YES'}
    
    return relevant_links



# Main function
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Example main link
        main_url = "https://kuznia-sulkowice.pl/"
        logging.info(f"Starting scraping process for main URL: {main_url}")

        # Initialize OpenAI API
        # openai = initialize_openai()

        # Step 2: Get all links from the main page
        all_links = await get_all_links(page, main_url)
        logging.info(f"Full links: {all_links}")
        print("All links:", all_links)

        # Step 3: Get relevant links
        relevant_links = await get_relevant_links(list(all_links))
        logging.info(f"Relevant links: {relevant_links}")
        print("Relevant links:", relevant_links)

        # Step 4: Filter URLs that have been marked as 'YES'
        yes_urls = filter_relevant_links(relevant_links)
        logging.info(f"Relevant URLs to scrape: {yes_urls}")
        print("Relevant URLs to scrape:", yes_urls)

        # Step 5: Scrape data from relevant URLs
        scraped_data = await scrape_data_from_urls(page, yes_urls)
        logging.info(f"Scraped data: {scraped_data}")
        print("Scraped data:", scraped_data)

        # Step 6: Clean scraped data before generating description
        cleaned_data = clean_and_format_scraped_data(scraped_data)
        logging.info(f"Cleaned data: {cleaned_data}")
        print("Cleaned data:", cleaned_data )

        # Step 6: Generate description
        description = await generate_description(cleaned_data)
        logging.info(f"Generated description: {description}")
        print("Generated description:", description)

        await browser.close()

if __name__ == "__main__":
    load_dotenv()
    print("Starting main function")

    asyncio.run(main())
