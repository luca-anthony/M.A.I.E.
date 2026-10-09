import time

import whisper
import queue
import sounddevice as sd
from faster_whisper import WhisperModel
import numpy as np
from kokoro import KPipeline as kpipe
import soundfile as sf

MODEL_SIZE = "large-v3"
DEVICE = "cuda"
SAMPLE_RATE = 16000
SILENCE_LIMIT = 1.5
THRESHOLD = 0.02 

print(f"Loading Whisper {MODEL_SIZE}...")
model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type="float16" if DEVICE == "cuda" else "int8")
print("System ready! Start speaking anytime (Press Ctrl+C to force quit).")

def capture_phrase():
    audio_buffer = []
    is_speaking = False
    silence_start_time = None
    
    def callback(indata, frames, time_info, status):
        nonlocal is_speaking, silence_start_time
        
        rms = np.sqrt(np.mean(indata**2))
        
        if rms > THRESHOLD:
            if not is_speaking:
                print("\nListening...")
                is_speaking = True
            silence_start_time = None  
            audio_buffer.append(indata.copy())
        else:
            if is_speaking:
                audio_buffer.append(indata.copy())
                if silence_start_time is None:
                    silence_start_time = time.time()
    
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, blocksize=4000, callback=callback):
        while True:
            if is_speaking and silence_start_time:
                if (time.time() - silence_start_time) > SILENCE_LIMIT:
                    print("Silence detected. Processing audio...")
                    break
            time.sleep(0.1)
            
    if audio_buffer:
        flat_audio = np.concatenate(audio_buffer).flatten()
        segments, _ = model.transcribe(flat_audio, language="en", beam_size=1)
        text_result = " ".join([segment.text for segment in segments]).strip()
        return text_result
    return ""

def listen_loop():
    try:
        while True:
            print("\n--- Waiting for speech ---")
            
            captured_text = capture_phrase()
            
            if captured_text:
                print(f"SAVED VARIABLE: \"{captured_text}\"")
                
            else:
                print("No clear speech detected.")
                
    except KeyboardInterrupt:
        print("\nProgram shut down cleanly.")

    return captured_text

if __name__ == "__main__":
    listen_loop()
