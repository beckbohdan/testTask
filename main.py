import json
import time
import re
from typing import List, Optional
from typing import TypedDict

import requests
from bs4 import BeautifulSoup

# Base URL for the listings page
base_url = "https://realtylink.org/en/properties~for-rent"

# Define custom headers with a user-agent to mimic a web browser
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

class Announcement(TypedDict):
    link: str
    ref: Optional[str]
    rent_period: Optional[str]
    type: Optional[str]
    title: Optional[str]
    address: Optional[str]
    region: Optional[str]
    description: Optional[str]
    images: List[str]
    price: Optional[str]
    bedrooms: Optional[int]
    bathrooms: Optional[int]
    floor_area: Optional[int]
    parking_spaces: Optional[int]
    additional_features: Optional[str]
    realtor: Optional[str]
    phone: Optional[str]
    latitude: Optional[str]
    longitude: Optional[str]


def fetch_page(session, url):
    response = session.get(url, headers=headers)
    response.raise_for_status()
    return response.text


def parse_announcement(session, announcement_url) -> Announcement:
    html = fetch_page(session, announcement_url)
    soup = BeautifulSoup(html, "html.parser")
    price_tag = soup.find("meta", itemprop="price")
    additional_features = extract_value_by_title(soup, "Additional Features")
    return Announcement(
        link=announcement_url,
        ref=get_text_or_default(soup.find("span", {"id": "ListingDisplayId"})),
        rent_period=extract_rent_period_and_type(soup)[0],
        type=extract_rent_period_and_type(soup)[1],
        title=get_text_or_default(soup.find("span", attrs={"data-id": "PageTitle"})),
        address=get_text_or_default(soup.find("h2", class_="pt-1")),
        region=parse_region(get_text_or_default(soup.find("h2", class_="pt-1"))),
        description=get_text_or_default(soup.find("div", itemprop="description")),
        images=extract_image_urls(soup),
        price=price_tag["content"] if price_tag else None,
        bedrooms=extract_number_from_tag(soup.find("div", class_="col-lg-3 col-sm-6 cac")),
        bathrooms=extract_number_from_tag(soup.find("div", class_="col-lg-3 col-sm-6 sdb")),
        floor_area=normalize_floor_area(extract_value_by_title(soup, "Floor Area")),
        parking_spaces=extract_value_by_title(soup, "Parking Spaces"),
        additional_features=extract_value_by_title(soup, "Additional Features"),
        realtor=get_text_or_default(soup.find("h1", class_="broker-info__broker-title")),
        phone=get_text_or_default(soup.find("a", itemprop="telephone")),
        latitude=get_text_or_default(soup.find("span", {"id": "PropertyLat"})),
        longitude=get_text_or_default(soup.find("span", {"id": "PropertyLng"}))
    )


def parse_region(full_address):
    if full_address:
        address_parts = full_address.split(",")
        if len(address_parts) >= 2:
            return ", ".join([address_parts[-2].strip(), address_parts[-1].strip()])
    return ""


def extract_image_urls(soup):
    pattern = r'window\.MosaicPhotoUrls\s*=\s*\[.*?\];'
    script_tag = soup.find("script", string=re.compile(pattern, re.DOTALL))
    if script_tag:
        image_urls_str = re.search(r'window\.MosaicPhotoUrls\s*=\s*(\[.*?\]);', script_tag.string, re.DOTALL)
        if image_urls_str:
            return json.loads(image_urls_str.group(1))
    return []


def extract_number_from_tag(tag):
    if tag:
        text = tag.text.strip()
        numbers = re.findall(r'\d+', text)
        if numbers:
            return int(numbers[0])
    return None


def get_text_or_default(tag, default=None):
    return tag.text.strip() if tag else default


def extract_value_by_title(soup, title):
    title_tag = soup.find("div", class_="carac-title", string=title)
    if title_tag:
        value_tag = title_tag.find_next_sibling("div", class_="carac-value")
        if value_tag:
            value_text = value_tag.text.strip()
            try:
                return int(value_text)
            except ValueError:
                return value_text
    return None


def normalize_floor_area(floor_area: Optional[str]) -> Optional[int]:
    result = None
    if floor_area:
        value_match = re.search(r'\b\d+(?:,\d+)*\b', floor_area)
        if value_match:
            result = int(value_match.group().replace(",", ""))
    return result


def extract_rent_period_and_type(soup):
    rent_period = None
    type_ = None

    price_container = soup.find("div", class_="price-container")
    if price_container:
        price_text = price_container.text.strip()
        if "month" in price_text.lower():
            rent_period = "month"
            type_ = "rent"
        elif "week" in price_text.lower():
            rent_period = "week"
            type_ = "rent"

    return rent_period, type_


def parse_announcements(url, limit=60) -> List[Announcement]:
    prefix = "https://realtylink.org"  # URL prefix for relative links
    announcements = []
    page_count = 0
    total_announcements = limit
    parsed_announcements = 0

    with requests.Session() as session:
        while len(announcements) < total_announcements:
            page_count += 1
            page_url = f"{url}&page={page_count}"  # Append page number to URL

            print(f"Start parsing page {page_count}")

            try:
                html = fetch_page(session, page_url)
                soup = BeautifulSoup(html, "html.parser")

                # Find all <a> elements within <div class="property-thumbnail-feature">
                links = soup.select('div.property-thumbnail-feature a.property-thumbnail-summary-link[href]')

                for link in links:
                    if len(announcements) >= limit:
                        break

                    announcement_url = prefix + link['href']
                    announcement = parse_announcement(session, announcement_url)
                    announcements.append(announcement)
                    parsed_announcements += 1
                    print(f"{parsed_announcements}/{total_announcements} parsed")

                # Add a delay (e.g., 1 second) to be respectful of the website's servers
                time.sleep(1)

            except requests.exceptions.RequestException as e:
                print(f"Error occurred during request: {e}")
                break

    return announcements


if __name__ == "__main__":
    url = f"{base_url}?view=Thumbnail&uc=1"

    # Parse up to 60 announcements
    announcements = parse_announcements(url, limit=60)

    if announcements:
        # Save the announcements as JSON
        with open("announcements.json", "w") as outfile:
            json.dump(announcements, outfile, indent=2)
        print(f"Successfully fetched and saved {len(announcements)} announcements to announcements.json.")
    else:
        print("No announcements were fetched or saved.")