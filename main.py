#TODO: Debug this function, code in debug works well.
#TODO: Add the regon verification
#TODO: Sync with google sheets and add the output to the sheet
#TODO: Test it.

from dotenv import load_dotenv
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from langchain.prompts.prompt import PromptTemplate
from langchain_openai import ChatOpenAI
from urllib.parse import urljoin
from urllib.parse import urljoin
import re
from output_parsers import relevant_links_parser
import unicodedata
import functions_framework
import requests


# Load the environment variables from .env
load_dotenv()


@functions_framework.http
def hello_http(request):
    """HTTP Cloud Function to scrape a website, verify REGON, and generate a description."""
        # Parse the JSON payload from the request
    request_json = request.get_json(silent=True)

    if request_json:
        row = request_json.get('row', 'No row provided')
        strona_www = request_json.get('strona_www', 'No URL provided')
        regon = request_json.get('regon', 'No REGON provided')

        def process_request():
            # Get all links from the main page
            all_links = get_all_links(strona_www)

            # Get relevant links using OpenAI
            relevant_links = get_relevant_links(list(all_links))

            # Filter URLs marked as 'YES'
            yes_urls = filter_relevant_links(relevant_links)

            # Scrape data from relevant URLs
            scraped_data = scrape_data_from_urls(yes_urls)

            # Clean scraped data
            cleaned_data = clean_and_format_scraped_data(scraped_data)

            # Generate description
            description = generate_description(cleaned_data)

            return {
                "description": description
            }

        return process_request()

# Helper functions

def get_all_links(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    full_links = set()
    phone_pattern = re.compile(r'^[\+\d\-\(\)\s]+$')
    email_pattern = re.compile(r'.+@.+\..+')
    keyword_pattern = re.compile(r'blog|publications', re.IGNORECASE)

    for a in soup.find_all('a', href=True):
        href = a.get('href').strip()
        if (
            href.startswith('mailto:') or
            href.startswith('tel:') or
            phone_pattern.match(href) or
            (email_pattern.match(href) and not href.startswith('mailto:')) or
            keyword_pattern.search(href)
        ):
            continue

        full_url = urljoin(url, href)
        full_links.add(full_url)

    return full_links

def get_relevant_links(urls):

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

    return res

# Function to filter relevant links
def filter_relevant_links(links_output):
    # Access the 'links' dictionary within the RelevantLinksOutput object
    links_dict = links_output.links
    
    # Filter links that are marked as 'YES'
    relevant_links = {url for url, relevance in links_dict.items() if relevance == 'YES'}
    
    return relevant_links

# Function to scrape data from urls
def scrape_data_from_urls(yes_urls):
    data = {}
    for url in yes_urls:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        data[url] = soup.get_text()
    return data

# TODO: Adjust cleaning for nip and regon
def clean_and_format_scraped_data(scraped_data):
    cleaned_data = {}
    nip_pattern = r'\bNIP\s*\d{3}[-\s]?\d{3}[-\s]?\d{2}[-\s]?\d{2}\b'
    regon_pattern = r'\bREGON\s*\d{9}\b'

    noisy_patterns = [
        r'\s+', 
        r'\b(Polityka prywatności|Zastrzeżenia|Wszelkie prawa zastrzeżone|Cookies)\b',
        r'(?:facebook|twitter|linkedin|instagram)\.com'
    ]

    repeated_block_patterns = [
        r'(\+?\d[\d\s\-\(\)]{7,})',
        r'\S+@\S+',
    ]

    for url, content in scraped_data.items():
        content = unicodedata.normalize("NFKD", content)
        content = re.sub(r'\s+', ' ', content).strip()

        nip_match = re.search(nip_pattern, content)
        regon_match = re.search(regon_pattern, content)
        nip = nip_match.group(0) if nip_match else ""
        regon = regon_match.group(0) if regon_match else ""

        for pattern in repeated_block_patterns:
            content = re.sub(pattern, '', content)
        for pattern in noisy_patterns:
            content = re.sub(pattern, '', content)

        lines = content.split('. ')
        seen = set()
        deduplicated_lines = []

        for line in lines:
            if line not in seen:
                seen.add(line)
                deduplicated_lines.append(line)

        content = '. '.join(deduplicated_lines)
        content = re.sub(r'\n{2,}', '\n', content)

        if nip:
            content += f"\nNIP: {nip}"
        if regon:
            content += f"\nREGON: {regon}"

        if content:
            cleaned_data[url] = content

    formatted_data = ""
    for url, content in cleaned_data.items():
        formatted_data += f"Source: {url}\nContent:\n{content}\n\n"

    return formatted_data

# Function to generate description
def generate_description(cleaned_data):

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
    return res_descripion
