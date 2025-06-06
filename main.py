import praw, re, time, json, logging, traceback, configparser, difflib
from datetime import date

#init
try:
  # read config and set variables
  with open('config.json') as config_file:
    config = json.load(config_file)
    config_client_id = config.get('client_id')
    config_client_secret = config.get('client_secret')
    reddit_username = config.get('reddit_username')
    reddit_password = config.get('reddit_password')
    subreddit_name = config.get('subreddit')
    support_flair_template_id = config.get('support_flair_template_id')
    solved_flair_template_id = config.get('solved_flair_template_id')
    bot_config_wiki_page = config.get('bot_config_wiki_page')
    bool_send_response = config.get('bool_send_response')
    log_level_terminal = config.get('log_level_terminal')
    log_level_file = config.get('log_level_file')
    log_level_api = config.get('log_level_api')
    log_retain_days = config.get('log_retain_days')

    logging.basicConfig(level=log_level_terminal, format='%(asctime)s %(levelname)s: %(message)s')
    today = date.today()
    file_handler = logging.FileHandler(f'logs-{today.strftime("%Y-%m-%d")}.log')
    file_handler.setLevel(log_level_file)
    file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
    logger = logging.getLogger()
    logger.addHandler(file_handler)

    logger.debug("Config read")

    if config.get('twofa_enabled'):
      twofa = input("Please provide 2FA token\n")
      print("twofa enabled. Read:", twofa.rstrip())

      if twofa:
        reddit_password = reddit_password + ":" + twofa.rstrip()

  reddit = praw.Reddit(
    client_id = config_client_id,
    client_secret = config_client_secret,
    username = reddit_username,
    password = reddit_password,
    user_agent = "PyEng Bot 0.1",
  )

  # stop PRAW and HTTP debug logs
  prawcore_logger = logging.getLogger("prawcore")
  prawcore_logger.setLevel(log_level_api)
  urllib3_logger = logging.getLogger("urllib3")
  urllib3_logger.setLevel(log_level_api)
  
  retry_delay = 30  
  subreddit = reddit.subreddit(subreddit_name)
  moderators = subreddit.moderator()
  
  config_wiki_page = subreddit.wiki[bot_config_wiki_page].content_md.strip()
  config_parser = configparser.ConfigParser()
  config_parser.read_string(config_wiki_page)
  config_wiki = config_parser['bot']

  support_regex_match_wiki_page = subreddit.wiki[config_wiki['support_regex_match_wiki_page_name']]
  support_regex_exclude_wiki_page = subreddit.wiki[config_wiki['support_regex_exclude_wiki_page_name']]
  support_match_patterns = support_regex_match_wiki_page.content_md.strip().split('\n')
  support_exclude_patterns = support_regex_exclude_wiki_page.content_md.strip().split('\n')
  
  logger.info(f"Init complete: logged in as {reddit_username} monitoring {subreddit_name}")
except Exception as e:
  logger.error(f"Encountered an exception during startup: {e}")
  quit()

def send_reply(response):
  if bool_send_response:
    logger.debug(f"Sending reply: {response}")
    comment.reply(response + '\n\n' + config_wiki['footer'])
  else:
    logger.info("Reply not sent as bool_send_response is false.")
    logger.info(f"Reply would've been: {response}")

def link_commands(type, search_data):
  startidx = body.find(f"!{type}") + len(f"!{type}")
  endidx = body.find("\n", startidx)
  argument = body[startidx:endidx].strip() if endidx != -1 else body[startidx:].strip()
  if type == "link" and ("ear" in argument or "phone" in argument):
    argument = argument.replace("nothing", "") #remove "nothing" from phone and ear searches
  logger.info(f"!{type} request for {argument} found")
  
  returned_link = None
  alt_aliases = []

  for search in search_data:
    alt_aliases.extend(search["aliases"])
    if argument in [alias for alias in search["aliases"]]:
      returned_link = search["link"]
      break

  if returned_link:
    return f"Here's the link for `{argument}`: {returned_link}"
  else:
    suggestions = difflib.get_close_matches(argument, [a for a in alt_aliases], n=3, cutoff=0.6)
    if suggestions:
      suggestion_lines = []
      for suggestion in suggestions:
        for search in search_data:
          if suggestion in search["aliases"]:
            suggestion_lines.append(f"* `{suggestion}`: {search["link"]}")
            break
      
      suggestion_block = "\n".join(suggestion_lines)
      return f"I couldn't an exact match for `{argument}`. Did you mean any of the following?\n\n{suggestion_block}"
    else:
      return f"I couldn't find a link for `{argument}` and no similar matches were found. If you think this is wrong, contact the mods."


while True:
  try:
    # for all comments in the subreddit
    for comment in subreddit.stream.comments(skip_existing=True):
        body = comment.body.lower()
        file_handler = logging.FileHandler(f'logs-{today.strftime("%Y-%m-%d")}.log')
        logger.info(f"Found comment in {subreddit}, {comment.id} in {comment.submission.id}")
        logger.debug(f"Comment from {comment.author}: {comment.body}")
        # check if the comment is the bot's
        if comment.author.name == reddit.user.me():
          continue
      
        # check for !solved in the body of a comment from OP or a mod of a submission
        if "!solved" in body and (comment.author == comment.submission.author or comment.author in moderators):
          logger.info("!solved found, changing flair")
          comment.submission.flair.select(solved_flair_template_id)
          send_reply(config_wiki['solved_response'])

        # check for !support in the body of a comment and respond with support links
        if "!support" in body:
          logger.info("!support found, responding with support links")
          response = f"u/{comment.parent().author.name}, here's how to get in touch with Nothing support:\n\n* Visit the [Nothing Support Centre](https://nothing.tech/pages/support-centre) and press the blue chat icon for live chat support (region and time dependent).\n* Visit the [Nothing Customer Support](https://nothing.tech/pages/contact-support) page to get in contact via web form.\n* Contact [\@NothingSupport on X](https://x.com/NothingSupport)."
          send_reply(response)

        if "!link" in body:
          with open("commands.json", "r") as j:
            json_data = json.load(j)
            search_data = json_data["link"]

          response = link_commands("link", search_data)
          
          if response:
            send_reply(response)

        if "!wiki" in body:
          with open("commands.json", "r") as j:
            json_data = json.load(j)
            search_data = json_data["wiki"]

          response = link_commands("wiki", search_data)
          
          if response:
            send_reply(response)

  except praw.exceptions.APIException as e:
    logger.error(f"Encountered an API exception: {e}")
    time.sleep(retry_delay)
  except Exception as e:
    logger.error(f"Encountered an exception: {e}")
    traceback.print_exc()
    time.sleep(retry_delay)
