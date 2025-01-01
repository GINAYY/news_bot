import discord
from discord.ext import commands, tasks
import requests
from bs4 import BeautifulSoup
import asyncio
from datetime import datetime
import pytz
import aiohttp
from googletrans import Translator
import os
from dotenv import load_dotenv
from keep_alive import keep_alive

# 加载环境变量
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))

# 设置机器人
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# 创建翻译器实例
translator = Translator()


class NewsFetcher:
    def __init__(self):
        self.seen_news = set()  # 用于存储已发送的新闻标题
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    # 获取 https://www.panewslab.com/zh/index.html 的新闻
    async def fetch_panewslab_news(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://www.panewslab.com/zh/index.html', headers=self.headers) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        news_items = []

                        # 根据网页结构选择新闻标题和描述
                        for article in soup.select('.pa-news__list-title'):
                            title = article.text.strip()  # 获取标题

                            # 获取描述
                            description_tag = article.find_next('p', class_='description')
                            description = description_tag.text.strip() if description_tag else '无描述'

                            # 如果新闻标题之前没发送过
                            if title not in self.seen_news:
                                self.seen_news.add(title)
                                news_items.append({
                                    'title': title,
                                    'description': description
                                })

                        return news_items
        except Exception as e:
            print(f"Error fetching Panewslab news: {e}")
            return []

    # 获取美联储、CPI、PPI、非农就业数据新闻
    async def fetch_gov_news(self):
        gov_sites = {
            'fed': 'https://www.federalreserve.gov/newsevents/pressreleases.htm',  # 美联储新闻
            'cpi': 'https://www.bls.gov/cpi/',  # 消费者物价指数 CPI
            'ppi': 'https://www.bls.gov/ppi/',  # 生产者物价指数 PPI
            'non_farm_jobs': 'https://www.dol.gov/newsroom/releases'  # 非农就业数据
        }

        news_items = []
        for site_name, url in gov_sites.items():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')

                            # 根据不同网站调整选择器
                            if site_name == 'fed':
                                articles = soup.select('.press-release-item')  # 美联储新闻
                            elif site_name == 'cpi':
                                articles = soup.select('.accordion-item')  # CPI新闻
                            elif site_name == 'ppi':
                                articles = soup.select('.accordion-item')  # PPI新闻
                            elif site_name == 'non_farm_jobs':
                                articles = soup.select('.release')  # 非农就业新闻

                            for article in articles:
                                title = article.select_one('.title').text.strip() if article.select_one('.title') else '无标题'
                                if title not in self.seen_news:
                                    content = article.select_one('.description').text.strip() if article.select_one('.description') else '无描述'
                                    time = article.select_one('.date').text.strip() if article.select_one('.date') else '无时间'

                                    # 翻译标题和内容
                                    title_zh = translator.translate(title, dest='zh').text
                                    content_zh = translator.translate(content, dest='zh').text

                                    self.seen_news.add(title)
                                    news_items.append({
                                        'source': site_name,
                                        'title': title_zh,
                                        'content': content_zh,
                                        'time': time
                                    })
            except Exception as e:
                print(f"Error fetching {site_name} news: {e}")

        return news_items


class NewsBot:
    def __init__(self, token, channel_id):
        self.token = token
        self.channel_id = channel_id
        self.news_fetcher = NewsFetcher()

    async def start(self):
        await bot.start(self.token)

    @tasks.loop(minutes=5)  # 每5分钟检查一次新闻
    async def check_news(self):
        channel = bot.get_channel(self.channel_id)
        if not channel:
            return

        # 获取来自 Panewslab 的新闻
        panewslab_news = await self.news_fetcher.fetch_panewslab_news()
        for news in panewslab_news:
            embed = discord.Embed(
                title=news['title'],
                description=news['description'],
                color=discord.Color.blue(),
                timestamp=datetime.now(pytz.UTC)
            )
            await channel.send(embed=embed)

        # 获取来自政府网站（美联储、CPI、PPI、非农就业数据）的新闻
        gov_news = await self.news_fetcher.fetch_gov_news()
        for news in gov_news:
            source_dict = {
                'fed': '美联储新闻',
                'cpi': '消费者物价指数',
                'ppi': '生产者物价指数',
                'non_farm_jobs': '非农就业数据'
            }
            embed = discord.Embed(
                title=f"[{source_dict.get(news['source'], '未知来源')}] {news['title']}",
                description=news['content'],
                color=discord.Color.green(),
                timestamp=datetime.now(pytz.UTC)
            )
            embed.add_field(name="发布时间", value=news['time'])
            await channel.send(embed=embed)


@bot.event
async def on_ready():
    print(f'Bot is ready! Logged in as {bot.user.name}')
    news_bot.check_news.start()


if __name__ == "__main__":
    # 创建并启动新闻机器人
    news_bot = NewsBot(DISCORD_TOKEN, DISCORD_CHANNEL_ID)
    keep_alive()
    asyncio.run(news_bot.start())