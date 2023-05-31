import praw, re, time, json, logging, urllib3
import pandas as pd
from datetime import date, datetime

### TO DO:
# change "adbotest" subreddit
# add NothingTechBot to https://www.reddit.com/prefs/apps/
# change "adbobot" username
# change "adbobot" password
# change flair_template_id for support and solved
# create wiki pages and change in config

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
    thanks_wiki_page_name = config.get('thanks_wiki_page')
    support_regex_match_wiki_page_name = config.get('support_regex_match_wiki_page')
    support_regex_exclude_wiki_page_name = config.get('support_regex_exclude_wiki_page')
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
  
  thanks_wiki_page = subreddit.wiki[thanks_wiki_page_name]
  thanks_wiki_contents = thanks_wiki_page.content_md
  
  support_regex_match_wiki_page = subreddit.wiki[support_regex_match_wiki_page_name]
  support_regex_exclude_wiki_page = subreddit.wiki[support_regex_exclude_wiki_page_name]
  support_match_patterns = support_regex_match_wiki_page.content_md.strip().split('\n')
  support_exclude_patterns = support_regex_exclude_wiki_page.content_md.strip().split('\n')
  
  logger.info("Init complete")
except Exception as e:
  logger.error("Encountered an exception during startup: {e}")
  quit()

def send_reply(response):
  logger.debug(f"Sending reply: {response}")
  footer = f"\n\n^(I'm a bot. Something wrong? Suggestions?) [^(Message the Mods)](https://www.reddit.com/message/compose?to=/r/{subreddit}&subject=Bot+feedback)"
  comment.reply(response + footer)

# check if they have a flair; if it's a star flair or a custom one
def handle_current_flair(user, new_points):
    user_flair_text = None
    # check if they have an existing flair and find the flair text
    for flair in subreddit.flair(user):
        logger.info("Found user's existing flair")
        if flair["flair_text"] is not None:
            user_flair_text = flair["flair_text"]
            logger.debug("Existing flair text is {user_flair_text}")
            break
    # if their flair text is nothing
    if not user_flair_text:
        logger.debug("No flair set yet")
        user_flair_text = f"★ {new_points}"
    # if a star already exists in the flair, increment the thanks count
    elif str("★") in user_flair_text:
        cur_points = int(user_flair_text.split(" ")[-1])
        logger.info("Thanks flair set, incrementing {str(cur_points)} to {str(new_points)}")
        user_flair_text = user_flair_text.replace(str(cur_points), str(new_points))
    else:
        logger.debug("Custom flair detected")
        user_flair_text = "custom"
        # # Check if user's custom flair already has a star
        # if any(char == "★" for char in user_flair_text):
        #     # Extract the current points value
        #     points = int(user_flair_text.split()[-1])
        #     print(f"Custom flair set, incrementing {str(points)}")
        #     # Append the new points value to the user's existing flair
        #     user_flair_text = user_flair_text.replace(str(points), str(points + 1))
        # else:
        #     # Append the star and points to the user's existing flair
        #     print("Custom flair set, appending thanks to 1")
        #     user_flair_text += " | ★ 1"
    return user_flair_text

# set flair if not custom
def set_flair(user_flair_text):
    points = user_flair_text.split()[-1]
    point_text = "point" if points == "1" else "points"
    if user_flair_text == "custom":
        response = f"Thanks for u/{user} registered. They now have {str(points)} {point_text}! However, this user has a custom flair so their level is not displayed."
        send_reply(response)
        logger.info("Custom flair set, thanks not added to flair")
    else:
        subreddit.flair.set(user, text=user_flair_text, flair_template_id=None)
        response = f"Thanks for u/{user} registered. They now have {str(points)} {point_text}!"
        send_reply(response)
        logger.debug("Thanks added to flair")

# extract the numeric value from the Level column
def get_level_num(level):
    if isinstance(level, str):
        level_num = level.split(" ")[-1]
        if level_num.isdigit():
            return int(level_num)
    return None

# get the wiki leaderboard
def get_wiki_leaderboard():
    # split markdown table string into rows
    rows = thanks_wiki_contents.strip().split("\n")[4:]
    # split each row into cells
    cells = [[cell.strip() for cell in row.split("|")[1:-1]] for row in rows]
    # create a pandas DataFrame from cells
    df = pd.DataFrame(cells, columns=["Username", "Level", "Last Star Date"])
    # convert 'Last Star Date' column to datetime type
    df["Last Star Date"] = pd.to_datetime(df["Last Star Date"]).dt.date

    return df

# set the wiki leaderboard, update or add user, level and date
def set_wiki_leaderboard(df, user_exists_in_leaderboard, user, points):
    user = f"u/{user}"
    today = date.today()
    if user_exists_in_leaderboard:
        # update the level and date cells on the row matching the username
        df.loc[df["Username"] == user, "Level"] = f"★ {points}"
        df.loc[df["Username"] == user, "Last Star Date"] = today.strftime("%Y-%m-%d")
    else:
        logger.debug("User not located in table")
        new_row = {
            "Username": user,
            "Level": f"★ {points}",
            "Last Star Date": today.strftime("%Y-%m-%d"),
        }
        df.loc[len(df)] = new_row

    # apply the function to create a new column with the numeric value of the Level column
    df["Level Num"] = df["Level"].apply(get_level_num)
    # sort the DataFrame by the Level Num column
    df = df.sort_values(by=["Level Num", "Last Star Date"], ascending=[False, True])
    # remove the Level Num column
    df = df.drop("Level Num", axis=1)
    # convert DataFrame back to markdown
    markdown_table = (
        f"This page is updated by a robot. Do not edit. *Last update*: {today.strftime('%Y-%m-%d')}\n\n" + df.to_markdown(index=False)
    )
    # overwrite subreddit wiki page with new markdown
    subreddit.wiki[thanks_wiki_page_name].edit(content=markdown_table)

# perform actions to thank - get wiki points, handle flair, set flair, set leaderboard
def thank_user(user):
  df = get_wiki_leaderboard()
  user_exists_in_leaderboard = df[df["Username"] == f"u/{user}"]
  if not user_exists_in_leaderboard.empty:
      logger.debug("User: {user} exists in leaderboard, so incrementing existing points")
      level = user_exists_in_leaderboard["Level"].iloc[0]
      last_star_date = user_exists_in_leaderboard["Last Star Date"].iloc[0]
      points = int(level.split(" ")[-1]) + 1
  else:
      logger.debug("User: {user} doesn't exist in leaderboard, so points = 1")
      points = 1
  user_flair_text = handle_current_flair(user, points)
  set_wiki_leaderboard(df, not user_exists_in_leaderboard.empty, user, points)
  set_flair(user_flair_text)

while True:
  try:
    # for all comments in the subreddit
    for comment in subreddit.stream.comments(skip_existing=True):
        logger.info(f"Found comment in {subreddit}")
        logger.debug(f"Comment from {comment.author}: {comment.body}")
        # check if the comment is the bot's
        if comment.author.name == reddit.user.me():
          continue
      
        # check if the comment body matches any of the match patterns if the flair ID = "Support" and the comment is from OP
        if comment.submission.link_flair_template_id == support_flair_template_id and comment.author == comment.submission.author:
          matched_pattern = None
          for pattern in support_match_patterns:
            match = re.search(pattern, comment.body, re.IGNORECASE)
            if match:
                matched_pattern = pattern
                logger.debug(f"Comment matched solved pattern: {matched_pattern}")
                break
          
          if matched_pattern is not None:
            # check if the comment body does not match any of the excluded patterns
            if not any(re.search(pattern, comment.body, re.IGNORECASE) for pattern in support_exclude_patterns):
              logger.info("Comment matched potential solved regex, so prompting to mark as solved")
              response = f"It seems like you might've resolved your issue. If so, please update the flair to 'Solved' or reply `!solved`\n\nIf you'd like to thank anyone for helping you, reply `!thanks` to *their* comment."
              send_reply(response)
            else:
               logger.debug("Comment matched exclude regex, so not responding")
      
        # check for !thanks in the body
        if "!thanks" in comment.body.lower():
          # check if the author is a mod
          if comment.author in moderators:
              logger.info(f"!thanks giver is a mod: {comment.author.name} in {comment.submission.id}")
              user = reddit.redditor(comment.parent().author.name)
              thank_user(user)
      
          # check if the submission flair ID = "Support" or "Solved" and that the comment is from OP
          elif (comment.submission.link_flair_template_id == support_flair_template_id or comment.submission.link_flair_template_id == solved_flair_template_id) and comment.author == comment.submission.author:
              user = reddit.redditor(comment.parent().author.name)
              logger.info(f"Found applicable !thanks from {comment.author} in {comment.submission.id}")
              has_been_thanked = False

              # check if the comment author is the same as the parent comment author, OP is replying to themselves
              if comment.parent().author == comment.author:
                  logger.info("OP is replying to themselves")
                  response = f"You can't thank yourself."
                  send_reply(response)
                  continue
              
              # check if the parent comment author is the bot
              if comment.parent().author.name == reddit.user.me():
                  response = f"Aw, thanks u/{comment.author.name}"
                  send_reply(response)
                  logger.info("User thanked bot")
                  continue
            
              # get all comments in the thread to check if thanks has already been given to this user
              submission = comment.submission
              submission.comments.replace_more(limit=None)
              logger.debug(f"Checking all comments in thread {comment.submission.id}")
              for comment_in_submission in submission.comments.list():
                # check for !thanks from OP
                if "!thanks" in comment_in_submission.body.lower() and comment_in_submission.author == comment.submission.author:
                  # get the user who has already been thanked
                  previously_thanked_user = comment_in_submission.parent().author
                  # if thanked user is the same as the newly thanked user
                  if previously_thanked_user == user:
                    for child_reply in comment_in_submission.replies:
                      logger.info(f"Found !thanks for {previously_thanked_user} - checking if has been thanked")
                      # check if there is already a thanks registered by the bot
                      if child_reply.author == reddit.user.me() and re.search(r"Thanks for .* registered\.", child_reply.body):
                          has_been_thanked = True
                          logger.info("!thanks already given in this thread")
                          break
                  if has_been_thanked:
                      break
                  
              # if they haven't already been thanked
              if not has_been_thanked:
                  thank_user(user)
              else:
                  response = f"You can only thank someone once per thread."
                  send_reply(response)
                  logger.info(f"Thanks not added as OP already thanked this user in this thread.")

        # check for !solved in the body of a comment from OP or a mod of a "Support" flaired submission
        if "!solved" in comment.body.lower() and comment.submission.link_flair_template_id == support_flair_template_id and (comment.author == comment.submission.author or comment.author in moderators):
          logger.info("!solved found, changing flair")
          comment.submission.flair.select(solved_flair_template_id)
          response = f"Thanks, I've marked your thread as solved. If this is incorrect, please revert the flair back to 'Support'.\n\nIf you'd like to thank anyone for helping you, reply `!thanks` to *their* comment."
          send_reply(response)

  except praw.exceptions.APIException as e:
    logger.error(f"Encountered an API exception: {e}")
    time.sleep(retry_delay)
  except Exception as e:
    logger.error(f"Encountered an exception: {e}")
    time.sleep(retry_delay)
