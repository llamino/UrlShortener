
import json
from urlshortener.models import ShortLink, Campaign
import os
def extract_links_data_to_models():
    file_path = os.path.join('json', 'links.json')
    print(file_path)
    with open(file_path, 'r', encoding='utf-8') as file:
        links = json.load(file)['links']

    campaign, created = Campaign.objects.get_or_create(name="Digikala")

    for link in links:
        if ShortLink.is_valid_url(link):
            short_link, created = ShortLink.objects.get_or_create(original_url=link, campaign=campaign)
            if created:
                print(f"Created ShortLink for {link}")
            else:
                print(f"ShortLink for {link} already exists")
        else:
            print(f"Invalid URL: {link}")


