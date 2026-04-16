import asyncio
import aiohttp
import json
import argparse
import os
import pandas as pd

SEARCH_URL = (
    "https://www.wildberries.ru/__internal/u-search/exactmatch/ru/common/v18/search"
)
USER_AGENT = os.getenv('user_agent')
AT_PAGE = 100


def getHeaders():
    return {
        "User-Agent": USER_AGENT,
        "x-requested-with": "XMLHttpRequest",
        "x-spa-version": "14.5.7",
        "x-userid": "0",
        "deviceid": "site_1fe50e9a624946d5b209778ab8e47efd",
        "x-queryid": "qid908552603177629231720260415223231",
    }

def getCookies():
    return {
        "_wbauid": os.getenv('_wbauid'),
        "x_wbaas_token": os.getenv('x_wbaas_token'),
        "routeb": os.getenv('routeb'),
        "_cp": "1",
    }





async def getProducts(query: str) -> list[dict]:
    """Получает товары с ВБ по запросу"""
    max_pages = 1
    current_page = 1

    products = []

    headers = getHeaders()

    cookies = getCookies()

    while current_page <= max_pages:

        params = {
            "ab_testing": "false",
            "appType": 1,
            "curr": "rub",
            "dest": -5843670,  # неясный параметр
            "hide_vflags": 4294967296,  # неясный параметр
            "lang": "ru",
            "query": query,
            "resultset": "catalog",
            "sort": "popular",
            "spp": 30,
            "suppressSpellcheck": "false",
            "page": current_page
        }

        async with aiohttp.ClientSession(headers=headers, cookies=cookies) as session:
            res = []
            result = await session.get(SEARCH_URL, params=params)
            
            if result.status != 200:
                raise Exception(result.status)
            t = await result.text()
            j = json.loads(t)

            if max_pages <= current_page:
                total = j.get("total", 0)
                print(f"total products {total}")
                max_pages = total // AT_PAGE + (1 if total % AT_PAGE > 0 else 0)

            if max_pages == 0:
                print("no results")
                break

            res = j.get("products", [])
            print(f"cur products: {len(products)}")
            print(f"products at page: {len(res)}")

            for item in res:
                product_card = await __getProductCard(item["id"], session)
                product = extractProductData(item, product_card)

                products.append(product)
                
            current_page += 1
            await asyncio.sleep(1)

            
    return products


async def __getProductCard(item_id: int, session: aiohttp.ClientSession) -> dict:
    """Получает словарь карточки товара по id"""

    part, vol = __getPartAndVol(item_id)

    result = {}

    card_url = f"https://spb-basket-cdn-04.geobasket.ru/vol{vol}/part{part}/{item_id}/info/ru/card.json"

    async with session.get(card_url) as response:
        if response.status == 200:
            text = await response.text()
            result = json.loads(text)
        else:
            print(f"card id {item_id} not found!")

    return result


def __getPartAndVol(item_id: int):
    """Получает vol и part из id"""
    item_id_str = str(item_id)
    vol_len = len(item_id_str) - 5
    part_len = len(item_id_str) - 3
    vol = item_id_str[:vol_len]
    part = item_id_str[:part_len]

    return part, vol


def __extractImagesFromData(item):
    """Собирает картинки в строку от 1 до pics"""
    images = []
    part, vol = __getPartAndVol(item["id"])

    for i in range(1, item["pics"] + 1):
        url_image = f"https://spb-basket-cdn-04.geobasket.ru/vol{vol}/part{part}/{item['id']}/images/big/{i}.webp"
        images.append(url_image)

    return images


def extractProductData(item: dict, card: dict) -> dict:
    """Собирает данные из карточки и элемента выдачи в одну структуру"""
    product = {}
    price = 0

    # берем первую цену из всех размеров
    for size in item["sizes"]:
        price = size["price"]["product"]
        break

    supplierUrl = f"https://www.wildberries.ru/seller/{item['supplierId']}"

    product = {
        "Артикул": item["id"],
        "Ссылка на товар": f"https://www.wildberries.ru/catalog/{item['id']}/detail.aspx",
        "Название": item["name"],
        "Рейтинг": float(item["reviewRating"]),
        "Количество отзывов": int(item["feedbacks"]),
        "Размеры": ",".join(list(map(lambda x: x.get("name"), item["sizes"]))),
        "Цена": price / 100,
        "Описание": card.get("description"),
        "Продавец": item["supplier"],
        "Ссылка на продавца": supplierUrl,
        "Количество": item["totalQuantity"],
    }

    product["Изображения"] = ",".join(__extractImagesFromData(item))

    for prop in card.get("options", []):
        product[prop["name"]] = prop["value"]

    return product


async def main():

    parser = argparse.ArgumentParser(description="Парсер WB")
    parser.add_argument("search_query", help="Поисковый запрос")

    args = parser.parse_args()
    if not args.search_query:
        raise ValueError("Поисковый запрос не может быть пустым")
    
    result = await getProducts(args.search_query)

    df = pd.DataFrame(result)
    df.to_excel('data.xlsx')


if __name__ == "__main__":
    asyncio.run(main())
