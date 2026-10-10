# M.A.I.E. setup, start to finish

Work through the phases in order. Each phase ends with a check so you know it worked before moving on.

## Phase 1: Test online mode on your PC

1. Install Python 3.11 or 3.12.
2. Install Ollama from ollama.com and sign in so cloud models work: `ollama signin`.
3. Put the project in a folder, open a terminal there, then:

       python -m venv .venv
       .venv\Scripts\activate          (Windows)
       . .venv/bin/activate            (Mac or Linux)
       pip install -r requirements-pc.txt

4. Copy `.env.example` to `.env`. Leave it empty if you use the signed-in local Ollama for cloud models.
5. Run text only first: `python main.py --mode online --text-only --no-tts`
6. Check: type a message and get a streamed reply. `/status` should show online as reachable.
7. Turn on voice: `python main.py --mode online`. Say "MAIE, hello". The first run downloads the Whisper model.
8. On Windows, kokoro speech needs espeak-ng installed. If you skip it, add Piper (`pip install piper-tts`) or use `--no-tts`.

If your cloud model name differs, edit `backends.online.model` in `config.json`. To call ollama.com directly instead of through the local app, set `backends.online.host` to `https://ollama.com`, put `OLLAMA_API_KEY` in `.env`, and use the model name without the `-cloud` suffix.

## Phase 2: Make your PC the brain for pc mode

1. Pull the model: `ollama pull gemma3:12b` (pick any model your GPU fits and set it in `backends.pc.model`).
2. Let Ollama listen on the network by setting the environment variable `OLLAMA_HOST=0.0.0.0:11434` and restarting Ollama.
   - Windows: System Properties, Environment Variables, add it, then quit and reopen Ollama.
   - Mac: `launchctl setenv OLLAMA_HOST "0.0.0.0:11434"` then restart Ollama.
   - Linux: `sudo systemctl edit ollama`, add `Environment="OLLAMA_HOST=0.0.0.0:11434"`, then `sudo systemctl restart ollama`.
3. Allow TCP port 11434 through the PC firewall for your private network only. Do not port-forward it on your router.
4. Give the PC a fixed address (router DHCP reservation) or use Tailscale in Phase 5.
5. Find the PC address and put it in `backends.pc.host`, for example `http://192.168.1.50:11434`.
6. Check from the PC: `python main.py --mode pc --text-only --no-tts`, then `/status`.

## Phase 3: Flash and prepare the Pi 5

1. Use the official 27W power supply and an active cooler.
2. In Raspberry Pi Imager choose Raspberry Pi OS (64-bit) with desktop. In the settings dialog set hostname `maie`, a username and password, your Wi-Fi, and enable SSH.
3. Boot, then `ssh youruser@maie.local` and run `sudo apt update && sudo apt full-upgrade -y && sudo reboot`.
4. Copy the project to the Pi, for example `git clone https://github.com/luca-anthony/M.A.I.E.` or `scp -r MAIE youruser@maie.local:~/`. Keep the folder name `MAIE` if you want to use the service file as written.
5. On the Pi: `cd ~/MAIE && ./scripts/setup_pi.sh`. This installs system packages, Ollama, the Python environment, a Piper voice, and the fallback model.
6. Edit `.env` and `config.json` as needed. Set `backends.pc.host` to your PC address.
7. Check: `. .venv/bin/activate && python main.py --mode local --text-only --no-tts`, send a message, and confirm a reply arrives (slow is normal on a Pi).
8. If the Pi has 4GB of RAM, change `backends.local.model` to `gemma3:1b` and run `ollama pull gemma3:1b`.

## Phase 4: Microphone and speaker

1. Plug in the USB mic and speaker, or use a USB audio adapter.
2. List devices: `python main.py --list-devices`.
3. Set `audio.input_device` and `audio.output_device` in `config.json` to the index or a unique part of the name. Set the output explicitly so sound never routes to the projector's HDMI audio.
4. Run `python main.py --mode local`. Say "MAIE, hello". If it does not hear you, lower `listen.min_level` or `listen.level_multiplier`. If it triggers on noise, raise them.
5. If the wake word is misheard, add the spelling you see printed after `You (voice):` to `wake.words`.

## Phase 5: Private network access

1. Install Tailscale on the Pi, the PC, and your phones, Mac, and iPad:

       curl -fsSL https://tailscale.com/install.sh | sh
       sudo tailscale up

2. Use the Tailscale name or address of the PC in `backends.pc.host` so pc mode works from anywhere.
3. Check: from your phone, open `http://maie:8096` after Phase 7 finishes.

## Phase 6: Camera

1. Connect the camera ribbon to the Pi 5 camera port with the Pi 5 cable, power off first.
2. Check: `rpicam-hello --list-cameras`.
3. Mount it pointing down at the desk. If the image is rotated, set `camera.rotate` to 90, 180, or 270.
4. Run `python main.py --mode local`, say "MAIE, what is this?" while holding something up. The last image is saved to `captures/last.jpg` so you can see what the model saw.
5. Camera Module 3 focuses poorly under about 10 cm. Mount it at least 25 cm above the desk.

## Phase 7: Hard drive and media server

1. Plug the drive into a USB 3 port using a powered enclosure or powered hub. A bare 3TB drive can brown out the Pi.
2. Find it: `lsblk -f`.
3. You have existing data, so keep it. If the drive is NTFS:

       sudo apt install -y ntfs-3g
       sudo mkdir -p /mnt/maie-drive
       sudo blkid
       echo 'UUID=YOUR-UUID /mnt/maie-drive ntfs-3g defaults,uid=1000,gid=1000,umask=022,nofail 0 0' | sudo tee -a /etc/fstab
       sudo mount -a

   Only reformat to ext4 (`sudo mkfs.ext4 /dev/sdX1`) if you have backed up everything, because it erases the drive.
4. Install Jellyfin: `curl https://repo.jellyfin.org/install-debuntu.sh | sudo bash`.
5. Open `http://maie.local:8096`, create an account, and add libraries pointing into `/mnt/maie-drive`.
6. The Pi 5 cannot hardware-transcode, so use clients that direct-play your files (Jellyfin apps on phone, Mac, iPad, or a TV box).
7. File sharing: `sudo apt install -y samba`, then append to `/etc/samba/smb.conf`:

       [maie]
       path = /mnt/maie-drive
       read only = no
       valid users = youruser

   Then `sudo smbpasswd -a youruser` and `sudo systemctl restart smbd`. Connect from other devices with `smb://maie.local/maie`.

## Phase 8: Projector

Micro-HDMI to HDMI is the right connection. It is direct, has no added latency, and is far better for hand tracking than any wireless casting. Details that matter:

- Use a short, good cable. Past about 3 to 5 metres use an active HDMI cable.
- Plug into either port, then open Screen Configuration on the Pi desktop and set the projector to its native resolution, arranged as a second display.
- If the projector is not detected or picks a wrong mode, force it by adding this to the end of the single line in `/boot/firmware/cmdline.txt` (check the port name with `wlr-randr`): `video=HDMI-A-1:1920x1080@60D`
- Keep audio off HDMI by setting `audio.output_device` as in Phase 4.

Steps:

1. Connect the projector and confirm the desktop appears on it.
2. Run `python main.py --list-devices` to see display sizes, and set `projector.display_index` (0 is the main display, 1 is the next).
3. Copy PNG, JPG, or PDF files into `projections/`.
4. In the program type `/project bracket` (partial names work). Press Esc on the projected window or type `/unproject` to clear it.
5. Mounted upside down or mirrored: set `projector.rotate` (0, 90, 180, 270) and `projector.flip`. Nudge alignment with `projector.scale`, `projector.offset_x`, and `projector.offset_y`.
6. Camera-to-projector alignment and focus are automatic, see the next two sections.

### Auto-calibration (camera to projector)

1. Mount the camera so it can see the whole projected area with a little margin. If it cannot see all of it, calibration fails.
2. Dim the room a little and clear the desk.
3. Type `/calibrate` or say "MAIE, calibrate". The projector shows a grid of markers for a few seconds. The camera finds them, computes the exact mapping between camera pixels and desk pixels, and saves it to `calibration.json`. On a Camera Module 3 it also autofocuses on the desk and locks the focus so your hands do not make it hunt.
4. The result reads like "12 markers, 0.6 pixel error, accuracy good". Under 5 pixels is good. The limit is `calibration.max_rms`.
5. `/calibrate check` tests whether the saved calibration still matches. Set `calibration.auto_on_start` to `true` to have M.A.I.E. check at every start and recalibrate only when needed.
6. Whenever you move the camera or projector, run `/calibrate` again. It takes about ten seconds.
7. If it fails, open `cache/calibration_debug.jpg` to see what the camera saw. Usual causes are a camera that cannot see the whole projection, too much room light, or a camera that is out of focus.
8. To test with a monitor instead of the projector, aim the camera at the monitor, set `profiles.pi.projector.fullscreen` to `true`, and set `projector.display_index` to the monitor number. Glare and screen patterns can raise the error a little.

Limits: this assumes a flat desk. A wide-angle camera lens bends straight lines, which shows up as a higher pixel error.

### Projector focus assist

1. Run `/focus`. The projector shows a fine checkerboard. The camera focus is locked first, so the readings measure the projector.
2. Turn the projector focus ring slowly past the sharpest point and then back. The tone rises in pitch as the image gets sharper, and a bar shows the sharpness at the center and four corners.
3. Stop when the center bar is full and the tone is at its highest. Type `/focus stop` to end it. It also ends by itself after two minutes. The microphone is muted while it runs.
4. If the corners stay well below the center at best focus, the projector is aimed at the desk at an angle and one side is out of the lens focus range. Reduce the angle, or pick the best compromise.

## Phase 9: 3D printer (Bambu Lab P2S)

OctoPrint does not work with Bambu printers. This project talks to the printer over the network using the `bambulabs_api` library.

1. On the printer, enable LAN mode and note the printer IP, access code, and serial number. Newer firmware may also require turning on Developer Mode for third-party control. Check Bambu's current wiki, since this changes between firmware versions.
2. Put the IP and serial in `config.json` under `printer`, set `printer.enabled` to `true`, and put the access code in `.env` as `MAIE_PRINTER_ACCESS_CODE`.
3. Export sliced files as `.3mf` from Bambu Studio into `prints/`.
4. Check: `/printer` should show the state and temperatures.
5. Print: `/print gear box`. M.A.I.E. asks you to confirm by saying or typing yes. It never starts a print without that.
6. Confirm the library supports your P2S before trusting it with a real print. Start with a small test file.

## Phase 10: Autostart on the Pi

    mkdir -p ~/.config/systemd/user
    cp deploy/maie.service ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable --now maie.service
    sudo loginctl enable-linger $USER

View logs with `journalctl --user -u maie -f`.

## Using the three modes

- `python main.py --mode online`, `--mode pc`, or `--mode local` to start in a mode.
- Switch while running: `/mode pc`, or say "MAIE, switch to local mode".
- In online and pc mode, if the target is unreachable M.A.I.E. automatically uses the local model and retries the target every few seconds, so it returns to the PC when the PC comes back.
- `/status` shows which backends are reachable.

## Troubleshooting

- No reply in pc mode: `curl http://PC_ADDRESS:11434/api/tags` from the Pi. If it fails, recheck Phase 2 steps 2 and 3.
- Slow local replies: use `gemma3:1b`, or shorten `max_history`.
- Speech model errors on the PC GPU: the code falls back to `small.en` on CPU. Set `stt.device` to `cpu` to force it.
- No voice output: check the line printed at startup beginning with `speech output`. Fix the missing piece or use `/voice off`.
- Projector window fails: read `cache/projector.log`.
