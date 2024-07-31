import discord
from discord.ext import commands, tasks
from discord.ui import Select, View
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import utc
from datetime import datetime, timedelta
import requests
import os
import random
import aiohttp
import asyncio
from openai import OpenAI
client = OpenAI()
from openai.types.chat import ChatCompletion, ChatCompletionUserMessageParam

# Load our token and channel ID from environment variables
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY')
NEWS_API_KEY = os.getenv('NEWS_API_KEY')
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
BASE_URL = "https://api.openbrewerydb.org/breweries"

# Playlist IDs
DAILY_MESSAGE_PLAYLIST_ID = "37i9dQZF1DXa41CMuUARjl"
JUKEBOX_PLAYLIST_ID = "1v2CenDfpQSR33n9bCwjwp"
OLDIE_PLAYLIST_ID = "16835A12xGrCA2D1eOYUuT"
SONG_PLAYLIST_ID = "1obCtVenuzS1sgHFZb7dgu"
RECOMMENDATION_PLAYLIST_ID = "37i9dQZF1DX0XUsuxWHRQd"

# Bot setup with intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Scheduler setup
scheduler = AsyncIOScheduler()
scheduler.configure(timezone=utc)

    
# Global variables for Spotify tracks
daily_message_tracks = []
jukebox_tracks = []
oldie_tracks = []
song_tracks = []

async def fetch_spotify_tracks(playlist_id):
    auth_url = "https://accounts.spotify.com/api/token"
    data = {
        'grant_type': 'client_credentials',
        'client_id': SPOTIFY_CLIENT_ID,
        'client_secret': SPOTIFY_CLIENT_SECRET
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(auth_url, data=data) as resp:
            auth_response = await resp.json()
            access_token = auth_response.get('access_token')
            if not access_token:
                print("Failed to retrieve access token")
                return []

    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    playlist_url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    async with aiohttp.ClientSession() as session:
        async with session.get(playlist_url, headers=headers) as resp:
            playlist_response = await resp.json()
            tracks = [
                item['track']['external_urls']['spotify']
                for item in playlist_response.get('items', [])
                if 'track' in item and item['track'] and 'external_urls' in item['track']
            ]
            return tracks

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}!')
    global daily_message_tracks, jukebox_tracks, oldie_tracks, song_tracks, recommendation_tracks
    daily_message_tracks = await fetch_spotify_tracks(DAILY_MESSAGE_PLAYLIST_ID)
    jukebox_tracks = await fetch_spotify_tracks(JUKEBOX_PLAYLIST_ID)
    oldie_tracks = await fetch_spotify_tracks(OLDIE_PLAYLIST_ID)
    song_tracks = await fetch_spotify_tracks(SONG_PLAYLIST_ID)
    recommendation_tracks = await fetch_spotify_tracks(RECOMMENDATION_PLAYLIST_ID)
    scheduler.start()
    scheduler.add_job(send_daily_message, 'cron', hour=13, minute=0)  # 6:00 AM PST is 13:00 UTC
    scheduler.add_job(check_weather, 'cron', hour=12, minute=58)  # 5:58 AM PST is 12:58 UTC

async def send_daily_message():
    global daily_message_tracks
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        if not daily_message_tracks:
            daily_message_tracks = await fetch_spotify_tracks(DAILY_MESSAGE_PLAYLIST_ID)
        random_link = random.choice(daily_message_tracks)
        quote = await fetch_quote()
        await channel.send(f"Daily Quote: {quote}\n\nGood Morning : ), here is your daily song: [Listen here]({random_link})")

async def fetch_quote():
    try:
        url = 'https://zenquotes.io/api/random'
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    quote = data[0]['q']
                    author = data[0]['a']
                    return f'"{quote}" - {author}'
                else:
                    print(f"Failed to fetch quote: {resp.status}")
                    return "Couldn't retrieve a quote at the moment."
    except Exception as e:
        print(f"An error occurred while fetching the quote: {str(e)}")
        return "An error occurred while retrieving the quote."


async def check_weather():
    forecast = await get_forecast()
    if forecast and will_rain(forecast):
        channel = bot.get_channel(CHANNEL_ID)
        if channel:
            await channel.send("It is going to rain today maybe wear a coat!\nHere's the weather update for South Gate, CA:")
            # Just taking the first entry as an example
            weather = forecast[0]
            await channel.send(f"Temperature: {weather['main']['temp']}°C / {weather['main']['temp']*9/5+32}°F\nWeather: {weather['weather'][0]['description']}")
#Weather Command- gives the weather in my city
@bot.command()
async def weather(ctx):
    weather = await get_weather()
    if weather:
        temp_celsius = weather['main']['temp']
        temp_fahrenheit = temp_celsius * 9/5 + 32
        await ctx.send(f"This is the weather in South Gate, CA:\nTemperature: {temp_celsius}°C / {temp_fahrenheit}°F\nWeather: {weather['weather'][0]['description']}")
    else:
        await ctx.send("Couldn't retrieve the weather information.")

async def get_weather():
    url = f"http://api.openweathermap.org/data/2.5/weather?q=South Gate,CA,90280,US&units=metric&appid={OPENWEATHER_API_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                print(f"Failed to get weather data: {resp.status}")
                return None

async def get_forecast():
    url = f"http://api.openweathermap.org/data/2.5/forecast?q=South Gate,CA,90280,US&units=metric&appid={OPENWEATHER_API_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json().get('list', [])
            else:
                print(f"Failed to get forecast data: {resp.status}")
                return None

def will_rain(forecast):
    rain_hours_utc = [(i + 13) % 24 for i in range(5, 22)]  # 5:00 AM to 9:00 PM PST in UTC
    for weather in forecast:
        dt = datetime.utcfromtimestamp(weather['dt'])
        if dt.hour in rain_hours_utc:
            if 'rain' in weather.get('weather', [{}])[0].get('main', '').lower():
                return True
    return False


#Test Command to test if bot is working!
@bot.command()
async def test(ctx):
    await ctx.send("I'm alive, darn it! : )")


@bot.command(name='spotify')
async def recommend_me(ctx):
    global recommendation_tracks
    if not recommendation_tracks:
        recommendation_tracks = await fetch_spotify_tracks(RECOMMENDATION_PLAYLIST_ID)
    recommendations = random.sample(recommendation_tracks, min(3, len(recommendation_tracks)))
    recommendation_message = "\n".join(f"[Listen here]({track})" for track in recommendations)
    await ctx.send(f"Here are 3 song recommendations based on my personal playlist:\n{recommendation_message}")
##!gives a song from Fallout All games!
@bot.command()
async def jukebox(ctx):
    global jukebox_tracks
    if not jukebox_tracks:
        jukebox_tracks = await fetch_spotify_tracks(JUKEBOX_PLAYLIST_ID)
    random_link = random.choice(jukebox_tracks)
    await ctx.send(f"Jukebox pick of the day: [Listen here]({random_link})")
#gives an oldie from a spotify playlist of my choosing!
@bot.command()
async def oldie(ctx):
    global oldie_tracks
    if not oldie_tracks:
        oldie_tracks = await fetch_spotify_tracks(OLDIE_PLAYLIST_ID)
    if oldie_tracks:
        random_link = random.choice(oldie_tracks)
        await ctx.send(f"Oldie but goodie: [Listen here]({random_link})")
    else:
        await ctx.send("No oldie tracks available")
#gives a random song from my favorite throwback playlist!
@bot.command()
async def song(ctx):
    global song_tracks
    if not song_tracks:
        song_tracks = await fetch_spotify_tracks(SONG_PLAYLIST_ID)
    random_link = random.choice(song_tracks)
    await ctx.send(f"Here's a song for you: [Listen here]({random_link})")

@bot.command()
async def brew(ctx):
    """Find the nearest 10 breweries based on city in California."""

    # Prompt user for city
    await ctx.send("Enter the city in California you'd like to search breweries in:")
    city_msg = await bot.wait_for('message', check=lambda message: message.author == ctx.author)
    city = city_msg.content.strip()  # Remove extra spaces

    # Build the API request URL with parameters (no API key needed)
    url = f"{BASE_URL}?by_city={city}&by_state=California&per_page=10"

    # Send an asynchronous HTTP GET request using aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                # Parse the JSON response from the API
                data = await response.json()
                if data:
                    # Craft a response message with brewery details (limit to 10)
                    response_msg = f"**Nearest Breweries in {city}, California:**\n"
                    for i, brewery in enumerate(data[:10]):  # Get only the first 10 breweries
                        brewery_name = brewery["name"]
                        brewery_city = brewery["city"]
                        brewery_state = brewery["state"]
                        response_msg += f"{i+1}. {brewery_name} - {brewery_city}, {brewery_state}\n"
                    await ctx.send(response_msg)
                else:
                    await ctx.send(f"Sorry, no breweries found in {city}, California.")
            else:
                # Handle API request errors
                await ctx.send(f"Error! Failed to retrieve brewery data. (Status code: {response.status})")

@bot.command()
async def news(ctx):
    # Ask for the search topic
    await ctx.send("What topic would you like to search for?")
    topic_msg = await bot.wait_for('message', check=lambda message: message.author == ctx.author)
    topic = topic_msg.content.strip()

    # Ask for the number of articles
    await ctx.send("How many articles would you like to see? (1-10)")
    num_msg = await bot.wait_for('message', check=lambda message: message.author == ctx.author)
    try:
        num_articles = int(num_msg.content)
        if num_articles < 1 or num_articles > 10:
            await ctx.send("Please enter a number between 1 and 10. Using default of 5.")
            num_articles = 5
    except ValueError:
        await ctx.send("Invalid input. Using default of 5 articles.")
        num_articles = 5

    # Fetch and send news
    await fetch_and_send_news(ctx, topic, num_articles)

async def fetch_and_send_news(ctx, query, num_articles):
    url = 'https://newsapi.org/v2/everything'
    params = {
        'q': query,
        'sortBy': 'publishedAt',
        'pageSize': num_articles,
        'apiKey': NEWS_API_KEY,
        'language': 'en'
        }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                news_data = await response.json()
                if news_data['status'] == 'ok' and news_data['articles']:
                    news_articles = news_data['articles']
                    for article in news_articles:
                        title = article['title']
                        url = article['url']
                        description = article['description']
                        message = f"**{title}**\n{description}\n{url}\n\n"
                        await ctx.send(message)
                else:
                    await ctx.send("No news articles found.")
            else:
                await ctx.send(f"Error fetching news: {response.status}")

@bot.command()
async def quote(ctx):
    try:
        response = requests.get('https://zenquotes.io/api/random')
        if response.status_code == 200:
            data = response.json()
            quote = data[0]['q']
            author = data[0]['a']
            await ctx.send(f'"{quote}" - {author}')
        else:
            await ctx.send("Failed to retrieve a quote. Please try again later.")
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")

@bot.command(name='ask')
async def ask(ctx, *, question):
    try:
        response: ChatCompletion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                ChatCompletionUserMessageParam(role="user", content=question)
            ]
        )
        answer = response.choices[0].message.content.strip()
        
        # Split the answer into chunks of 2000 characters or less
        chunks = [answer[i:i+2000] for i in range(0, len(answer), 2000)]
        
        for chunk in chunks:
            await ctx.send(chunk)
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")

@bot.command(name='joke')
async def joke(ctx):
    try:
        url = "https://official-joke-api.appspot.com/random_joke"
        response = requests.get(url).json()
        await ctx.send(f"{response['setup']} - {response['punchline']}")
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")

bot.run(os.getenv('DISCORD_TOKEN'))
