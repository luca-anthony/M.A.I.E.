import ollama
from voiceInputOutput import capture_phrase
from voiceInputOutput import listen_loop

print("Welcome to M.A.I.E.! Type 'exit' to quit.")

def input_response(user_input):
    response = ollama.chat(
        model='gemma4:31b-cloud',
        messages=[
            {
                'role': 'user',
                'content': user_input
            }
        ]
    )
    print("M.A.I.E.:", response['message']['content'])

ai_running = True
while ai_running: 
    user_input = input("Message: ") or listen_loop()
    if user_input.lower() == 'exit':
        ai_running = False
    else:
        input_response(user_input)