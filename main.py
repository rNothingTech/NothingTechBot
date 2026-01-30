import praw, time, json, logging, traceback, configparser, difflib, re, string, yaml, os
from datetime import date
from praw.models import Submission

#init
try:
  # read config and set variables
  with open('config.json', 'r') as config_file:
    config = json.load(config_file)
    config_client_id = config['client_id']
    config_client_secret = config['client_secret']
    reddit_username = config['reddit_username']
    reddit_password = config['reddit_password']
    subreddit_names = config['subreddit'].replace(' ', '')
    solved_flair_template_ids = config['solved_flair_template_ids']
    # bot_config_wiki_page = config['bot_config_wiki_page']
    bool_send_response = config['bool_send_response']
    log_level_terminal = config['log_level_terminal']
    log_level_file = config['log_level_file']
    log_level_api = config['log_level_api']
    log_retain_days = config['log_retain_days']

    logging.basicConfig(level=log_level_terminal, format='%(asctime)s %(levelname)s: %(message)s')
    today = date.today()
    file_handler = logging.FileHandler(f'logs/log-{today.strftime("%Y-%m-%d")}.log')
    file_handler.setLevel(log_level_file)
    file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
    logger = logging.getLogger()
    logger.addHandler(file_handler)

    logger.debug("Config read")

    if config['twofa_enabled']:
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
  
  retry_delay = 10
  subreddit = reddit.subreddit(subreddit_names.replace(' ', ''))
  first_subreddit = reddit.subreddit(subreddit_names.split('+')[0])

  # map list of mods in each sub
  moderators_map = {}
  for subreddit_name in subreddit_names.split('+'):
    sub = reddit.subreddit(subreddit_name)
    try:
      moderators_map[subreddit_name] = list(sub.moderator())
    except Exception as e:
      logger.error(f"Failed to get moderators for {subreddit_name}: {e}")
      quit()

  # log the moderators map for each subreddit
  for subreddit_name, moderators in moderators_map.items():
    if moderators:
      logger.debug(f"Subreddit: {subreddit_name} moderators: {[mod.name for mod in moderators]}")
    else:
      logger.debug(f"Subreddit: {subreddit_name} has no moderators or could not be fetched.")
  
  with open('bot_config.txt', 'r') as bot_config_file:
    config_wiki_page = bot_config_file.read().strip()

  # config_wiki_page = first_subreddit.wiki[bot_config_wiki_page].content_md.strip()
  config_parser = configparser.ConfigParser()
  config_parser.read_string(config_wiki_page)
  config_wiki = config_parser['bot']

  support_regex_match_wiki_page = first_subreddit.wiki[config_wiki['support_regex_match_wiki_page_name']]
  support_regex_exclude_wiki_page = first_subreddit.wiki[config_wiki['support_regex_exclude_wiki_page_name']]
  support_match_patterns = support_regex_match_wiki_page.content_md.strip().split('\n')
  support_exclude_patterns = support_regex_exclude_wiki_page.content_md.strip().split('\n')
  
  logger.info(f"Init complete: logged in as {reddit_username} monitoring {subreddit_names}")
except Exception as e:
  print(f"Encountered an exception during startup: {e}")
  quit()

commands_path = "commands.yaml"
commands_data = {}
commands_mtime = 0

def load_commands_if_updated():
  global commands_data, commands_mtime
  try:
    current_mtime = os.path.getmtime(commands_path)
    if current_mtime > commands_mtime:
      with open(commands_path, "r") as f:
        commands_data = yaml.safe_load(f)
      commands_mtime = current_mtime
      logger.info(f"Reloaded {commands_path} (modified at {current_mtime})")
  except Exception as e:
      logger.error(f"Error loading YAML: {e}")

def send_reply(comment, response):
  response = response.replace("<user>", f"u/{comment.author.name}")

  if bool_send_response:
    logger.debug(f"Sending reply: {response}")
    comment.reply(response + '\n\n' + config_wiki['footer'])
  else:
    logger.info("Reply not sent as bool_send_response is false.")
    logger.info(f"Reply would've been: {response}")

def add_comment(comment, content, submission, sticky):
  logger.info(f"Adding comment to {submission.id}")
  new_comment = submission.reply(content + '\n\n' + config_wiki['footer'])
  if sticky:
    new_comment.mod.distinguish(sticky=True)

def is_command_quoted(comment_body, command) -> bool:
  # check if the command is surrounded by quotes (", ', `)
  pattern = rf"""(\\)*([\"'`])\s*{command}\s*\1*\2"""

  return bool(re.search(pattern, comment_body))

def sanitise_command(argument):
  # remove words
  remove_words = config_wiki['remove_words'].split(', ')
  pattern = r'\b(?:' + '|'.join(map(re.escape, remove_words)) + r')\b'
  argument = re.sub(pattern, '', argument, flags=re.IGNORECASE)

  # remove emotes like :) :P etc
  emoticon_pattern = r'[:;=8][-^]?[)D(\]/\\OpP]'
  argument = re.sub(emoticon_pattern, '', argument)

  # remove emoji using unicode ranges
  emoji_pattern = r'[' \
                u'\U0001F600-\U0001F64F'  \
                u'\U0001F300-\U0001F5FF'  \
                u'\U0001F680-\U0001F6FF'  \
                u'\U0001F1E0-\U0001F1FF'  \
                u'\U00002700-\U000027BF'  \
                u'\U0001F900-\U0001F9FF'  \
                u'\U00002600-\U000026FF'  \
                ']+'
  argument = re.sub(emoji_pattern, '', argument)

  # remove punctuation
  argument = argument.translate(str.maketrans('', '', string.punctuation))

  argument = re.sub(r'\s+', ' ', argument).strip()
  return argument

def link_commands(type, search_data, comment_body):
  # find the start + end index based on !command and new line
  startidx = comment_body.find(f"!{type}") + len(f"!{type}")
  endidx = comment_body.find("\n", startidx)
  # get the argument based on startidx and endidx, or just startidx
  argument = comment_body[startidx:endidx].strip() if endidx != -1 else comment_body[startidx:].strip()

  if not argument:
    logger.debug(f"!{type} request found but no argument specified. Full body: {comment_body}")

    if type == "glyph":
        return ("You can view all community Glyph projects here: https://reddit.com/r/NothingTech/wiki/library/glyph-projects/\n\n"
              "You can also use this command to find specific Glyph projects, e.g. `!glyph bngc` or `!glyph glyphtones`.")
    elif type == "app":
        return ("You can view all community apps here: https://reddit.com/r/NothingTech/wiki/library/community-apps/\n\n"
              "You can also use this command to find specific apps, e.g. `!app simone` or `!app glyphify`.")
    elif type == "wiki":
        return ("Here's the link to our wiki: https://reddit.com/r/NothingTech/wiki\n\n"
              "You can also use this command to find specific topics, e.g. `!wiki nfc icon` or `!wiki phone chargers`.")
    elif type == "toy":
        return ("You can view all community toys here: https://www.reddit.com/r/NothingTech/wiki/library/glyph-projects/#wiki_community_glyph_matrix_toys\n\n"
              "You can also use this command to find specific toys, e.g. `!toy magic 8 ball` or `!toy counter`.")
    elif type == "link":
        return ("You can view all of Nothing's official links here: https://reddit.com/mod/NothingTech/wiki/library/official-links\n\n"
              "You can also use this command to find specific links, e.g. `!link phone (3a)` or `!link nothing discord`.")
    elif type == "firmware":
        return ("You can view the main community-maintained stock Nothing OS Firmware Repository here: https://github.com/spike0en/nothing_archive\n\n"
              "You can also use this command to find specific topics, e.g. `!firmware root` or `!firmware unbrick`.")  
      
  argument = sanitise_command(argument)
  logger.info(f"!{type} request for {argument} found")

  # too many spaces to be a search argument
  if (type == "wiki" or type == "glyph" or type == "app" or type == "toy") and argument.count(" ") > 4:
    return config_wiki['wiki_no_match_footer']
  if type == "link" and argument.count(" ") > 2:
    return config_wiki['link_no_match_footer ']
  
  returned_link = None
  alt_aliases = []

  for search in search_data:
    # add all the aliases to the alt_aliases list for searching
    alt_aliases.extend(search['aliases'])
    # check if the agument exact matches any aliases
    if argument in [alias for alias in search['aliases']]:
      returned_display_name = search['display_name']
      returned_link = search['link']
      break

  if returned_link:
    if type == "wiki":
      # if this is linking to a specific section of the wiki page
      if "#" in returned_link:
        return (f"Here's the link for **[{returned_display_name}]({returned_link})**.\n\n"
                f"This is a part of the page: {returned_link.split('#')[0]}\n\n"
                f"{config_wiki['wiki_footer']}")
      else:
        return f"Here's the link for `{returned_display_name}`: {returned_link}\n\n{config_wiki['wiki_footer']}"
    else:
      footer = ""
      if type == "app":
        footer = '\n\n' + config_wiki['app_footer']
      elif type == "glyph" or type == "toy":
        footer = '\n\n' + config_wiki['glyph_footer']

      # return links for everything that isn't wiki (link, glyph, app)
      return f"Here's the link for `{returned_display_name}`: {returned_link}{footer}"
  else:
    # get close matches for the argument vs the aliases
    suggestions = difflib.get_close_matches(argument, [a for a in alt_aliases], n=3, cutoff=0.6)
    if suggestions:
      suggestion_lines = []
      added_suggestions = set()
      for suggestion in suggestions:
        for search in search_data:
          if suggestion in search['aliases']:
            # if we didn't already add this one, add it to the suggestions
            if search['display_name'] not in added_suggestions:
              suggestion_lines.append(f"* `{search['display_name']}`: {search['link']}")
              added_suggestions.add(search['display_name'])
            break
      
      suggestion_block = "\n".join(suggestion_lines)
      return f"I couldn't an exact match for `{argument}`. Did you mean any of the following?\n\n{suggestion_block}"
    else:
      footer = config_wiki['link_no_match_footer'] if type == "link" else config_wiki['wiki_no_match_footer']
      return f"I couldn't find a link for `{argument}` and no similar matches were found. If you think this is wrong, contact the mods.\n\n{footer}"

while True:
  try:
    # for all comments in the subreddit
    for comment in subreddit.stream.comments(skip_existing=True):
        body = comment.body.lower()
        file_handler = logging.FileHandler(f'logs/log-{today.strftime("%Y-%m-%d")}.log')
        logger.info(f"Found comment in {subreddit}, {comment.id} in {comment.submission.id}")
        logger.debug(f"Comment from {comment.author}: {comment.body}")
        subreddit_name = comment.subreddit.display_name
        subreddit_mods = moderators_map.get(subreddit_name, [])
        
        # check if the comment is the bot's
        if comment.author.name == reddit.user.me():
          continue
      
        # check for !solved in the body of a comment from OP or a mod of a submission, set solved flair
        if "!solved" in body and (comment.author == comment.submission.author or any(mod.name == comment.author.name for mod in subreddit_mods)):
          logger.info("!solved found, checking if quoted")
          if not is_command_quoted(body, "!solved"):
            logger.info("not quoted, changing flair")
            subreddit_name = comment.submission.subreddit.display_name
            comment.submission.flair.select(solved_flair_template_ids.get(subreddit_name))
            send_reply(comment, config_wiki['solved_response'])
        elif "!solved" in body:
          if comment.author == comment.submission.author:
            logger.debug("!solved found and author is OP")
          elif any(mod.name == comment.author.name for mod in subreddit_mods):
            logger.debug("!solved found and author is a mod")
          else:
            logger.debug("!solved found but author is not OP or a mod, ignoring")

        # check for !answer in the body of a comment from OP or a mod of a submission, set solved flair and comment the solution
        if "!answer" in body and (comment.author == comment.submission.author or any(mod.name == comment.author.name for mod in subreddit_mods)):
          logger.info("!answer found, checking if quoted")
          if not is_command_quoted(body, "!answer"):
            logger.info("not quoted, generating reply and changing flair")
            # check if there's a valid parent comment
            if isinstance(comment.parent(), Submission):
              send_reply(comment, "You can only reply `!answer` to a comment providing the answer to your question. Did you mean `!solved`?")
            else:
              # can't set the bot as the answer
              if comment.parent().author == reddit.user.me():
                send_reply(comment, "You can't set the bot's comment as the answer. Please use `!solved` to change the flair to solved.")
              else:
                if comment.author != comment.submission.author and any(mod.name == comment.author.name for mod in subreddit_mods):
                  content = (
                    "Mod u/{} marked the following comment as the best answer on behalf of u/{}:\n\n"
                    "> {}\n\n"
                    "> \\- by u/{} - [Jump to comment]({})"
                  ).format(
                    comment.author.name,
                    comment.submission.author.name,
                    comment.parent().body.replace("\n\n", "\n\n> "),
                    comment.parent().author.name,
                    comment.parent().permalink
                  )
                else:
                  content = (
                    "u/{} marked the following comment as the best answer:\n\n"
                    "> {}\n\n"
                    "> \\- by u/{} - [Jump to comment]({})"
                  ).format(
                    comment.author.name,
                    comment.parent().body.replace("\n\n", "\n\n> "),
                    comment.parent().author.name,
                    comment.parent().permalink
                  )

                add_comment(comment, content, comment.submission, True)
                subreddit_name = comment.submission.subreddit.display_name
                comment.submission.flair.select(solved_flair_template_ids.get(subreddit_name))
                send_reply(comment, config_wiki['answer_response'])
        elif "!answer" in body:
          if comment.author == comment.submission.author:
            logger.debug("!answer found and author is OP")
          elif any(mod.name == comment.author.name for mod in subreddit_mods):
            logger.debug("!answer found and author is a mod")
          else:
            logger.debug("!answer found but author is not OP or a mod, ignoring")

        # check for !support in the body of a comment and respond with support links
        if "!support" in body:
          logger.info("!support found, checking if quoted")
          if not is_command_quoted(body, "!support"):
            logger.info("not quoted, responding with support links")
            response = f"u/{comment.parent().author.name}, here's how to get in touch with Nothing support:\n\n* Visit the [Nothing Support Centre](https://nothing.tech/pages/support-centre) and press the blue chat icon for live chat support (region and time dependent).\n* Visit the [Nothing Customer Support](https://nothing.tech/pages/contact-support) page to get in contact via web form.\n* Contact [\@NothingSupport on X](https://x.com/NothingSupport)."
            send_reply(comment, response)

        # check for !bug or !feedback in the body of a comment and respond with support links
        bug_commands = ["!bug", "!bugs", "!feedback"]
        matched_bug_command = next((cmd for cmd in bug_commands if cmd in body), None)
        if matched_bug_command:
          logger.info(f"{matched_bug_command} found, checking if quoted")
          if not is_command_quoted(body, matched_bug_command):
            logger.info("not quoted, responding with support links")
            response = f"u/{comment.parent().author.name}, be sure to submit bugs and feedback requests through your phone's Settings > System > Feedback menu."
            send_reply(comment, response)

        # check for !link, !wiki, !glyph, !firmware or !app in the body of a comment and respond with the relevant link
        json_commands = ["!link", "!linkme", "!wiki", "!faq", "!glyph", "!glyphs", "!app", "!apps", "!toy", "!toys", "!firmware"]
        matched_link_command = next((cmd for cmd in json_commands if cmd in body), None)
        if matched_link_command:
          logger.info(f"{matched_link_command} found, checking type")
          
          if matched_link_command == "!link" or matched_link_command == "!linkme":
            command_type = "link"
          elif matched_link_command == "!wiki" or matched_link_command == "!faq":
            command_type = "wiki"
          elif matched_link_command == "!glyph" or matched_link_command == "!glyphs":
            command_type = "glyph"
          elif matched_link_command == "!app" or matched_link_command == "!apps":
            command_type = "app"
          elif matched_link_command == "!toy" or matched_link_command ==  "!toys":
            command_type = "toy"
          elif matched_link_command == "!firmware":
            command_type = "firmware"

          logger.info(f"Command type: {command_type}, checking if quoted")
          if not is_command_quoted(body, f"!{command_type}"):
            logger.info(f"Not quoted, doing {command_type} command")
            
            load_commands_if_updated()
            search_data = commands_data.get(command_type, [])

            response = link_commands(command_type, search_data, body)
            
            if response:
              send_reply(comment, response)

  except praw.exceptions.APIException as e:
    logger.error(f"Encountered an API exception: {e}")
    time.sleep(retry_delay)
  except Exception as e:
    logger.error(f"Encountered an exception: {e}")
    traceback.print_exc()
    time.sleep(retry_delay)
