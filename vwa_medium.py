import base64, asyncio, os
from dotenv import load_dotenv
from typing import Annotated, Sequence, List, TypedDict, Union
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import json
import argparse

browser = Union[Browser, None] 
page = Union[Page, None]
browser_context: Union[BrowserContext, None] 

class Config(TypedDict):
    link: str
    interests: list[str]
    scroll_count: int

# defining the state dictionary which will be passed between nodes
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages] 
    url: Union[str, None]
    current_ss: Union[List[str], None]
    summaries: Annotated[Sequence[BaseMessage], add_messages]
    scroll_decision: Union[str, None]
    task: str

# Browser Util Functions
async def initialize_browser():
    """
    Initialize a new Chromium browser without using existing profiles.
    """
    global browser, page, browser_context
    print('-----Initializing new Chromium browser instance-----')

    try:
        pw = await async_playwright().start()
        
        # Launch fresh Chromium without any profile
        browser = await pw.chromium.launch(headless=False)
        browser_context = await browser.new_context()
        page = await browser_context.new_page()
        
        print('-----Chromium browser initialized-----')

    except Exception as e:
        print(f'Failed to initialize browser: {e}')

async def close_browser():
    """
    Closes only the Chromium browser, not any existing Chrome
    """
    global browser, browser_context, page

    try:
        if page:
            await page.close()
        if browser_context:
            await browser_context.close()
        if browser:
            await browser.close()
        print('-----Chromium browser closed-----')
    except Exception as e:
        print(f'Error closing browser: {e}')
    finally:
        browser = None
        browser_context = None
        page = None

async def close_login_popup_if_present():
    """
    Closes Medium login popup if it appears
    """
    global page

    if page is None:
        return

    try:
        # Common Medium popup close button selectors
        close_selectors = [
            "button[aria-label='Close']",
            "button[title='Close']", 
            "button:has-text('Close')",
            ".js-close",
            "[data-testid='close-button']",
            "button svg[data-testid='close']"
        ]

        for selector in close_selectors:
            try:
                close_button = await page.wait_for_selector(selector, timeout=1000)
                if close_button:
                    await close_button.click()
                    print(f"✅ Closed login popup using: {selector}")
                    await asyncio.sleep(1)
                    return
            except:
                continue

        # Try pressing Escape key to close popup
        await page.keyboard.press('Escape')
        print("Pressed Escape to close popup")

    except Exception as e:
        print(f"Error closing popup: {e}")

# Tools
@tool
async def navigate_url(url: str) -> str:
    """
    This tool takes the browser to navigate to the URL provided via Playwright.
    """
    global page
    print('-----Navigating to the provided URL-----')
    try: 
        await page.goto(url, wait_until = 'domcontentloaded')  
        # await asyncio.sleep(2)
        return f'-----Successfully Navigated-----'  
      
    except Exception as e:
        return f'The Error that occured during navigating url is:{e}'

# return type is string because we are using base64 
# Screenshot with Playwright, return raw binary image data(like PNG bytes)
# b64_ss = base64.b64encode(binary_ss) converts to bas64 format and returns it as bytes
# .decode("utf-8") converts bytes object to a python string, ie, prinatable ASCII
@tool
async def take_ss() -> str:
    """
    Takes screenshot of the current browser state via Playwright.
    """

    global page

    if page is None:
        return '-----Browser page not initialized-----'
    
    else:
        print('*****ACTION: taking screenshot of the current browser state*****') 

        try:
            binary_ss = await page.screenshot()
            b64_ss = base64.b64encode(binary_ss).decode("utf-8")

            print('-----Screenshot successfully captured-----')
            return b64_ss
        
        except Exception as e:
            return f'Error that occured during taking screenshot:{e}' 

@tool
async def scroll_down() -> str:
    """
    Scrolls the page down by a fixed amount.
    """

    global page

    if page is None:
        return "-----Page not initialised-----"

    viewport_height = await page.evaluate("window.innerHeight")
    scroll_amount   = int(viewport_height * 0.8)

    await page.evaluate(f"window.scrollBy(0, {scroll_amount});")
    await asyncio.sleep(0.1)  # small wait for loading dynamic content

    return f"*****Scrolled {scroll_amount}px*****"

# Initialize VLM with tools
agent_tools = [navigate_url, take_ss, scroll_down]
llm = ChatGoogleGenerativeAI(
    model='gemini-2.5-flash',
    google_api_key=os.environ['GEMINI_API_KEY']
).bind_tools(tools=agent_tools)

# Nodes
async def init_node(state: AgentState) -> AgentState:
    """
    Initializes fresh Chromium browser and navigates to URL
    """
    print('-----Initial Node-----')
    
    await initialize_browser()  # Changed function name
    navigate_output = await navigate_url.ainvoke(config['link'])

    interests_text = ', '.join(config['interests'])
    task = f"Analyze this Medium article and give a brief overview"

    return {
        **state,
        'url': config['link'],
        'task': task,
        'messages': [SystemMessage(content=f'Navigated to: {config["link"]}. {navigate_output}')]
    }

async def ss_node(state: AgentState) -> AgentState:
    """
    Takes a screenshot of the current page using the take_ss tool
    and stores it in the state as a list.
    """

    print('-----Screenshot Node-----')
    try:
        b64_ss = await take_ss.ainvoke(input=None) # LangChain tools require an input parameter even if it's None:
        print("*****Screenshot captured and returned from tool*****")

        current_ss_list = state.get("current_ss") 
        if current_ss_list is None:
            current_ss_list = []

        current_ss_list.append(b64_ss)

        updated_messages = state.get("messages") + [
            SystemMessage(content="Screenshot captured and saved to state.")
        ]

        return {
            **state,
            "current_ss": current_ss_list,
            "messages": updated_messages,
        }

    except Exception as e:
        error_msg = f"Error during ss_node: {e}"
        print(error_msg)
        return {
            **state,
            "messages": [SystemMessage(content = error_msg)]
        }

async def summarizer_node(state: AgentState) -> AgentState:
    """
    Uses the LLM to summarize the current screenshot and page state.
    The latest screenshot is sent as a base64 image to the model.
    """

    print("-----Summarizer Node-----")
    task = state.get("task", "Summarize this page as briefly as possible") # The prompt
    screenshots = state.get("current_ss")

    if not screenshots:
        print("-----No screenshot available to summarize-----")
        return {
            **state,
            "summaries": state.get("summaries", []) + [SystemMessage(content="No screenshot available for summarization.")]
        }

    latest_ss = screenshots[-1]  # Only use the most recent one

    user_prompt = HumanMessage(content=[
        {"type": "text", "text": f"Summarize this screenshot for the following task:{task}"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{latest_ss}"}}
    ])

    try:
        summary = await llm.ainvoke([user_prompt])
        print("*****LLM summarization successful*****")

        return {
            **state,
            "summaries": state.get("summaries", []) + [summary],
            "messages": state.get("messages", []) + [SystemMessage(content="Page summary generated.")],
        }

    except Exception as e:
        error_msg = f"Error during summarization: {e}"
        print(error_msg)
        return {
            **state,
            "messages": state.get("messages", []) + [SystemMessage(content=error_msg)],
        }

async def scroll_decision_node(state: AgentState) -> AgentState:
    """
    Scrolls and closes popups if they appear
    """
    global page
    if page is None:
        return {**state,
                "messages": state["messages"] + [SystemMessage(content="Scroll skipped – page not initialised.")]}
    
    # Close any login popups first
    await close_login_popup_if_present()
    
    # How far down are we now?
    before = await page.evaluate("window.scrollY")

    tool_result = await scroll_down.ainvoke(input=None)

    after = await page.evaluate("window.scrollY")
    moved = after - before

    # Check for popups again after scrolling
    await close_login_popup_if_present()

    return {**state,
            "messages": state["messages"] + [SystemMessage(content=f"{tool_result}  (Δy = {moved}px)")]}

async def aggregate_node(state: AgentState) -> AgentState:
    """
    Aggregates summaries and provides recommendation
    """
    print("-----Aggregation Node-----")
    summaries = state.get("summaries", [])
    interests_text = ', '.join(config['interests'])

    # Create comprehensive prompt
    summary_content = "\n\nArticle Summaries:\n" + "\n\n".join([msg.content for msg in summaries if hasattr(msg, "content")])
    
    recommendation_prompt = [
        SystemMessage(content=f"""
        Based on the article summaries given here, provide:
        1. A comprehensive summary of the article
        2. A clear YES/NO recommendation with reasoning on whether this article is worth reading for someone interested in: {interests_text}
        3. You do not need to navigate to any url. Just use summaries given to you.
        
        Format your response as:
        SUMMARY: [your summary]
        RECOMMENDATION: YES/NO - [reasoning]
        """),
        HumanMessage(content=summary_content)
    ]

    try:
        final_response = await llm.ainvoke(recommendation_prompt)
        
        return {
            **state,
            "messages": state["messages"] + [
                SystemMessage(content="Final analysis completed."), 
                HumanMessage(content=final_response.content)
            ]
        }

    except Exception as e:
        return {
            **state,
            "messages": state["messages"] + [SystemMessage(content=f"Error during aggregation: {e}")],
        }

# Node Router
def route_scroll_decision(state: AgentState) -> str:
    """
    Smart routing: stops if no scroll movement OR after max attempts
    """
    messages = state.get("messages", [])
    
    # Check for browser failure
    init_failed = any("Browser initialization failed." in msg.content for msg in messages if isinstance(msg, SystemMessage))
    if init_failed:
        return "decide_aggregate"
    
    # Count scrolls
    scroll_count = sum(1 for msg in messages if "Scrolled" in msg.content)
    if scroll_count >= config['scroll_count']:
        print("Reached maximum scroll attempts.")
        return "decide_aggregate"
    
    # Check if last scroll actually moved
    for msg in reversed(messages):
        if "Δy = " in msg.content:
            try:
                scroll_amount = int(msg.content.split("Δy = ")[1].split("px")[0])
                if scroll_amount == 0:
                    print("Reached end of page (no scroll movement).")
                    return "decide_aggregate"
            except:
                pass
    
    # If no browser failure/exceeding scroll count/reached page end, then scroll
    print(f"Scroll count: {scroll_count}, continuing to scroll.")
    return "decide_scroll"

workflow = StateGraph(AgentState)

# Nodes
workflow.add_node("init", init_node)
workflow.add_node("screenshot", ss_node)
workflow.add_node("summarizer", summarizer_node)
workflow.add_node("decide_scroll", scroll_decision_node)
workflow.add_node("scroll", lambda state: scroll_down.ainvoke(input=None).then(lambda _: state))
workflow.add_node("aggregate", aggregate_node)

# Entry
workflow.set_entry_point("init")

# Flow
workflow.add_edge("init", "screenshot")
workflow.add_edge("screenshot", "summarizer")
workflow.add_edge("summarizer", "decide_scroll")

workflow.add_conditional_edges(
    "decide_scroll",
    route_scroll_decision,
    {
        "decide_scroll": "screenshot",     # loop
        "decide_aggregate": "aggregate"    # exit
    }
)

workflow.add_edge("aggregate", END)

app = workflow.compile()

# To run the graph and stream it
async def run_graph():
    initial_state = {
        "messages": [],
        "url": None,
        "current_ss": [], # Initialize as empty list to store base64 strings of screenshot images
        "summaries": [],  # Initialize as empty list to store summary messages
        "scroll_decision": None,
        "task": "" 
    }
    print("\n--- Starting LangGraph Agent ---\n")

    try:
        # Using astream to see the state changes step-by-step
        # Set recursion_limit to prevent infinite loops in case of unexpected behavior
        async for step in app.astream(initial_state, {"recursion_limit": 100}): 
            step_name = list(step.keys())[0]
            print(f"\n--- Step: {step_name} ---")

            latest_state = step[step_name]

            if step_name == "summarizer":
                # Find the latest summary message added by the summarizer
                if latest_state.get('summaries'):
                    latest_summary_message = latest_state['summaries'][-1] # the last one
                    if isinstance(latest_summary_message, (AIMessage, HumanMessage)) and latest_summary_message.content:
                         print(">>> Individual Screenshot Summary:")
                         print(latest_summary_message.content)
                    elif isinstance(latest_summary_message, SystemMessage):
                         print(">>> Summarizer Status:", latest_summary_message.content)

            elif step_name == "decide_scroll":
                decision = latest_state.get('scroll_decision')
                print(f">>> Scroll Decision: {decision}")

            elif step_name == "aggregate":
                # The aggregation node adds the final summary as a HumanMessage to the messages list
                final_summary_message = None
                # Iterate backwards through messages to find the latest summary-like message
                for msg in reversed(latest_state.get('messages', [])):
                    # Since the aggregation node adds a SystemMessage "Final summary created." just before the HumanMessage
                    if isinstance(msg, HumanMessage) and final_summary_message is None:
                         final_summary_message = msg # Potential final summary
                    elif isinstance(msg, SystemMessage) and msg.content == "Final analysis completed." and final_summary_message is not None:
                         # Found the system message preceding a potential summary, so this is the final summary
                         print(">>> Final Aggregated Summary:")
                         print(final_summary_message.content)
                         break 

                # Fallback in case the heuristic fails or no valid summary was produced
                if final_summary_message is None:
                     print(">>> Aggregation Node Finished (No valid final summary found in messages).")
                     # You could add logic here to print a specific error message from state['messages'] if aggregation failed

    except Exception as e:
        print(f"\n--- An error occurred during graph execution: {e} ---")
    finally:
        print("\n--- Agent execution finished. Attempting to close browser. ---")
        await close_browser()

# parsing config
def parse_config():
    """Parse config from command line or default"""
    parser = argparse.ArgumentParser(description='Visual web agent for Medium articles')
    parser.add_argument('--config', type=str, help='JSON config string')
    parser.add_argument('--link', type=str, help='Article link')
    parser.add_argument('--interests', nargs='+', help='List of interests')
    parser.add_argument('--scroll_count', type=int, default=3, help='Max scroll count')
    
    args = parser.parse_args()
    
    if args.config:
        return json.loads(args.config)
    else:
        return {
            'link': args.link ,
            'interests': args.interests or ['AI', 'Technology'],
            'scroll_count': args.scroll_count
        }


if __name__ == "__main__":
    # Global config
    config = parse_config()
    print(f"Starting with config: {config}")
    try:
        asyncio.run(run_graph())
    except KeyboardInterrupt:
        print("\n--- Interrupted by user ---")
    except Exception as e:
        print(f"\n--- Unexpected error: {e} ---")
    finally:
        pass

