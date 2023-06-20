import os
import threading
import time
import re
import concurrent.futures
from fpdf import FPDF
from dotenv import load_dotenv
import tiktoken
from tqdm import tqdm
import openai
from flask import Flask, request, render_template

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
applicantName = "Alejandro A. Garcia Polo"
header = """Alejandro A. Garcia Polo
273 Lester St.
Waterloo, Ontario, N2L 3W6
June 19, 2023

"""

def numTokensFromString(string: str) -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(str(string)))
    return num_tokens

def updateCostFile(cost: float) -> None:
    """Updates the costTracking.txt file with the new cost."""
    if not os.path.exists("costTracking.txt"):
        with open("costTracking.txt", "w") as f:
            f.write("0")
    
    with open("costTracking.txt", "r") as f:
        current_cost = float(f.read().strip())

    new_cost = current_cost + cost

    with open("costTracking.txt", "w") as f:
        f.write(str(new_cost))
def askGpt(prompt, gpt4):
    conversation = [{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": prompt}]
    
    # Calculate available tokens for the response
    prompt_tokens = numTokensFromString(prompt)
    max_allowed_tokens = 4000  # Set the maximum allowed tokens
    available_tokens_for_response = max_allowed_tokens - prompt_tokens

    # Ensure the available tokens for the response is within the model's limit
    if available_tokens_for_response < 1:
        raise ValueError("The input query is too long. Please reduce the length of the input query.")
    
    max_retries = 4
    for _ in range(max_retries + 1):  # This will try a total of 5 times (including the initial attempt)
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4" if gpt4 else "gpt-3.5-turbo",
                messages=conversation,
                max_tokens=available_tokens_for_response,
                n=1,
                stop=None,
                temperature=0.1,
            )

            message = response.choices[0].message["content"].strip()

            # Count tokens
            response_tokens = numTokensFromString(message)
            total_tokens = prompt_tokens + response_tokens

            # Calculate cost
            cost_per_token = 0.06 if gpt4 else 0.002
            cost = (total_tokens / 1000) * cost_per_token

            # Update the cost file
            updateCostFile(cost)

            return message
        
        except Exception as e:
            if _ < max_retries:
                print(f"Error occurred: {e}. Retrying {_ + 1}/{max_retries}...")
                time.sleep(1)  # You can adjust the sleep time as needed
            else:
                raise

def create_cover_letter(job_description, main_resume):
    try:
        print("Recieved")
        # Call askGpt with the job description and main resume
        cover_letter_text = askGpt(
            f"I need help making a high quality cover letter, before asking you that, here is my resume please learn it\"{main_resume}\"\n Here is the job description, please write a final cover letter I can send and do not ever lie about my qualifications, and no place holders please: {job_description}",
            True  # change this to false if you want to use gpt-3.5-turbo
        )

         # Add a newline after the first comma following "Dear Hiring"
        cover_letter_text = re.sub(r"(Dear Hiring[^,]*,)", r"\1\n", cover_letter_text, 1)

        match = re.search(r"(Dear Hiring.*?(?=(Sincerely|Best regards),))", cover_letter_text, re.DOTALL)
        if match:
            cover_letter_text = match.group(1) + "\n" + cover_letter_text[match.end():]
            cover_letter_text += "\n"
            cover_letter_text += applicantName
        else:
            print("No valid cover letter format found. Check the text again.")
        # Extract the position name from the job description
        match = re.search(r"(\w+\s\w+)\sposition", job_description)
        position_name = match.group(1) if match else "default"
        print(position_name)
        cover_letter_text = (header + cover_letter_text)
        # Create PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Times", size=11)
        # pdf.cell(200, 10, txt=cover_letter_text, ln=True)
        # Split the cover letter into words
        words = cover_letter_text.split()
        
        # Add words to the PDF one by one
        line = ""
        for word in words:
            if "\n" in word:
                # If the word contains a newline, split it into two parts: before and after the newline
                before_newline, after_newline = word.split("\n", 1)
                
                # Add the part before the newline to the current line and add the line to the PDF
                test_line = f"{line} {before_newline}"
                pdf.multi_cell(0, 5, txt=test_line, align='J')
                
                # Add a blank line to the PDF
                pdf.multi_cell(0, 5, txt="")
                
                # Start a new line with the part after the newline
                line = after_newline
            else:
                # If the word does not contain a newline, add it to the current line
                test_line = f"{line} {word}"
                if pdf.get_string_width(test_line) > pdf.w - 2*pdf.l_margin:
                    # If adding the word would make the line too long, add the current line to the PDF and start a new one
                    pdf.multi_cell(0, 5, txt=line, align='J')
                    line = word
                else:
                    # If adding the word would not make the line too long, add it to the current line
                    line = test_line

        # Add the last line to the PDF
        pdf.multi_cell(0, 5, txt=line, align='J')
        if not os.path.exists('cover letters'):
            os.makedirs('cover letters')

        # Generate unique filename
        filename = f"cover letters/{position_name}.pdf"
        counter = 1
        while os.path.isfile(filename):
            filename = f"cover letters/{position_name} ({counter}).pdf"
            counter += 1
        pdf.output(filename)
        print("Completed")

    except Exception as e:
        print(f"Error occurred when creating cover letter: {e}")

def start_application_process():
    # Read mainResume from file
    with open("textResume.txt", "r") as f:
        main_resume = f.read()

    while True:
        job_description = input("Please paste the job description here (or type 'exit' to finish):\n")

        if job_description.lower() == 'exit':
            break

        create_cover_letter(job_description, main_resume)






@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        job_description = request.form['job_description']

        # Read mainResume from file
        with open("textResume.txt", "r") as f:
            main_resume = f.read()

        # Run in a separate thread so it doesn't block the server
        threading.Thread(target=create_cover_letter, args=(job_description, main_resume)).start()

        return render_template('index.html', message='Job application started!')

    return render_template('index.html')

if __name__ == "__main__":
    app.run(debug=True)