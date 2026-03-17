# Event-Triggered Audio Replay Agent

## Architecture

I2S microphone
   ↓
ESP32-S3 node
   - I2S capture
   - PCM framing
   - UDP audio uplink
   - MQTT control and telemetry
   ↓
PC audio hub
   - UDP receiver
   - 10 min ring buffer
   - replay window extraction
   ↓
Audio analysis pipeline
   - VAD
   - STT
   - keyword / audio event detection
   - structured summary
   ↓
Home Assistant + agent
   - event trigger
   - decision
   - notify / remember / act


## Summary

This document records a practical project idea for a home AI assistant system that uses short-term audio replay instead of constant full-time transcription.

The core idea is to give a home agent a contextual "ear" without turning the whole house into a permanent surveillance pipeline. Microphone nodes continuously capture audio and upload it to a central PC hub, where only a short rolling buffer is retained, for example the most recent 10 minutes. The system does not continuously transcribe everything. Instead, it waits for meaningful home events, such as a door opening, a package arrival, or a motion trigger. When such an event happens, the agent selectively retrieves the relevant audio window around that event and analyzes it.

This turns raw audio sensing into event-aware perception.

## Motivation

Typical home AI assistants are easy to reproduce at a superficial level:

- always-on microphone
- wake word
- speech-to-text
- simple LLM orchestration
- Home Assistant tool calls

That stack is useful, but ordinary. It behaves like a voice assistant with home automation hooks.

This project aims at something more valuable:

- lower privacy cost than always-on transcription
- lower compute cost than full continuous ASR
- stronger contextual reasoning than a plain voice assistant
- better alignment with real home events

The goal is not "hear everything." The goal is "listen only when context says listening matters."

## Core Concept

Each microphone endpoint in the home continuously captures audio and streams it to a central PC hub over UDP. The PC hub maintains an overwrite-based circular buffer and only retains a limited recent window, such as 10 minutes. No long-term archive is created by default.

When a relevant event occurs in Home Assistant, the system uses that event as a trigger to:

1. identify the affected area or device
2. retrieve a time window around the event from the PC hub ring buffer for the nearest microphone node
3. run analysis on that short audio segment
4. convert the result into structured observations
5. let the agent decide whether to notify, remember, infer, or act

This is similar in spirit to "instant replay" systems in gaming, but applied to household audio and contextual decision making.

## Example Scenario

One concrete example is food delivery handling.

1. The front door lock opens or the front door contact sensor changes state.
2. Home Assistant emits an event indicating a front-door interaction has started.
3. The system retrieves audio from the front-door microphone node.
4. It extracts a replay window such as:
   - 30 seconds before the event
   - 90 seconds after the event
5. It analyzes the window for:
   - speech activity
   - speech transcription
   - keywords such as "delivery", "package", "left at the door", "thank you"
   - optional non-speech events such as knock, footsteps, lingering presence
6. The agent produces a structured interpretation.
7. The system may then:
   - notify the user that delivery was detected
   - add a memory entry
   - ignore the event if nothing meaningful happened
   - flag suspicious behavior if someone remained outside for too long

The system is therefore not just listening. It is aligning sound with household context.

## Why This Is Useful

### Privacy

The design avoids default permanent storage of household conversations. Audio is only preserved temporarily inside a ring buffer. Analysis happens only when relevant context exists.

This is far more defensible than indiscriminate full-time transcription.

### Compute Efficiency

Speech recognition is expensive compared with simple audio buffering and voice activity detection. By only analyzing short windows around meaningful events, the system avoids wasting compute on irrelevant background noise.

### Better Contextual Intelligence

A normal assistant only reacts to direct commands. This design allows the agent to reason about short lived situations:

- a delivery handoff
- someone speaking at the door
- an unusual argument near the hallway
- a child crying in another room
- a glass-break event after a motion trigger

The agent gains selective perception rather than blind always-on transcription.

## Architecture Overview

The system can be divided into four layers.

### 1. Microphone Node Layer

Each room or zone can host a small audio capture node built around ESP32-S3 and an I2S microphone.

Responsibilities:

- capture audio continuously
- package PCM audio into fixed-size frames
- uplink audio continuously to the PC hub over UDP
- expose control and telemetry through MQTT
- optionally perform lightweight local statistics or preprocessing

Preferred behavior:

- keep the node simple and real-time safe
- avoid long-lived storage on the node
- treat UDP as the audio data plane
- treat MQTT as the control and status plane

Possible hardware:

- ESP32-S3
- I2S digital microphone such as INMP441 or similar
- optional PSRAM-equipped board variant for larger buffers or future local preprocessing

### 2. PC Audio Hub Layer

This layer receives the live audio stream and turns it into short-term replayable context.

Responsibilities:

- receive UDP audio packets from one or more microphone nodes
- reorder or detect loss using packet sequence numbers and timestamps
- maintain a per-node rolling ring buffer, such as 10 minutes
- extract replay windows on demand
- optionally materialize temporary WAV or PCM files for analysis

This layer is the short-term memory of the system. It keeps replay local and bounded without pushing long-duration storage requirements onto the embedded nodes.

### 3. Event Trigger Layer

This layer listens to structured events from Home Assistant and other sensors.

Possible triggers:

- door opened
- lock unlocked
- doorbell pressed
- package detected
- motion detected
- mmWave presence event
- alarm state changed
- unusual sensor combination

Each trigger creates an analysis request that includes:

- event type
- source device
- location
- start time
- replay window definition
- priority or risk level

The trigger layer does not handle audio directly. Its role is to request a time window from the PC audio hub when context indicates that listening is useful.

### 4. Audio Analysis Layer

This layer processes only the extracted short replay segment.

Potential analysis steps:

1. VAD to isolate speech regions
2. ASR to obtain transcript
3. keyword spotting
4. non-speech audio event detection
5. optional speaker recognition
6. structured summarization

This layer should output machine-usable observations, not just raw text.

Example output:

```json
{
  "event": "front_door_opened",
  "window_start": "2026-03-16T12:01:04Z",
  "window_end": "2026-03-16T12:03:04Z",
  "speech_detected": true,
  "transcript": "Your delivery is here. I left it at the door.",
  "keywords": ["delivery", "left at the door"],
  "audio_events": ["knock", "footsteps"],
  "confidence": 0.88,
  "summary": "Likely package delivery interaction at the front door."
}
```

### 5. Agent Decision Layer

An agent runtime such as OpenClaw can consume the structured output and decide what to do next.

Possible actions:

- send a notification
- update a memory store
- ask a follow-up question
- trigger a Home Assistant action
- ignore low-value events
- escalate risky or abnormal events

This is where audio understanding becomes "assistant behavior."

## Communication Model

The communication model is intentionally split into two planes.

### UDP Data Plane

UDP carries the continuous audio stream from ESP32-S3 nodes to the PC hub.

Recommended first-pass format:

- 16 kHz
- 16-bit PCM
- mono
- fixed packet duration such as 20 ms

Each packet should include:

- node identifier
- packet sequence number
- capture timestamp
- sample rate and format metadata
- PCM payload

This keeps the audio path simple and low-latency.

### MQTT Control Plane

MQTT carries low-rate control and status traffic.

Typical uses:

- node availability
- Wi-Fi signal strength
- uptime
- stream enabled or disabled
- target host or port updates
- restart or maintenance commands
- Home Assistant MQTT discovery

Audio itself should not be transported over MQTT.

## Relationship to OpenClaw

OpenClaw is not the source of the audio capability. It is the orchestration and reasoning layer above it.

In this design, OpenClaw would gain a new sensory path:

- it does not hear everything directly
- it receives contextual replay analyses
- it can request more details when needed
- it can combine audio results with Home Assistant state, memory, and user preferences

This effectively gives the agent a selective ear rather than an uncontrolled always-on microphone feed.

## Difference From a Typical Voice Assistant

This project is not just another wake-word assistant.

Typical voice assistant:

- waits for wake word
- transcribes current speech
- maps command to action

This project:

- buffers audio continuously
- waits for contextual events
- replays a relevant time window
- analyzes speech and non-speech signals
- reasons over the event in household context

The second design is much closer to environmental understanding than command recognition.

## Privacy and Safety Principles

This project should be designed around strict default constraints.

Recommended rules:

- no permanent raw audio retention by default
- rolling overwrite buffer only
- replay extraction only for approved event types
- explicit room-level opt-in
- no background full-time transcription
- no automatic sensitive action without confirmation
- clear audit trail for every replay and every agent decision

Sensitive zones such as bedrooms or bathrooms should likely be excluded entirely, or handled with far stricter policy.

## Recommended MVP

The first version should be narrow and practical.

### MVP Goal

Detect and summarize front-door delivery interactions.

### MVP Components

1. One front-door microphone node
2. PC hub rolling audio buffer for the last 10 minutes
3. Home Assistant trigger on:
   - door open
   - doorbell press
   - package-related event if available
4. Replay extraction window:
   - 30 seconds before
   - 90 seconds after
5. Analysis pipeline:
   - VAD
   - ASR
   - keyword spotting for delivery-related phrases
6. Structured summary output
7. Notification or log entry in Home Assistant or OpenClaw

### MVP Success Criteria

- correctly captures the relevant audio window after a door event
- transcribes short human interaction with acceptable quality
- identifies likely delivery scenarios
- produces a concise machine-readable summary
- does not require full-time transcription

## Suggested Output Schema

The analysis result should be standardized so multiple agent systems can consume it.

```json
{
  "analysis_id": "uuid",
  "source_node": "front_door_mic",
  "location": "front_door",
  "trigger_event": "door_opened",
  "trigger_time": "2026-03-16T12:01:34Z",
  "replay_window": {
    "pre_seconds": 30,
    "post_seconds": 90
  },
  "speech_detected": true,
  "transcript_segments": [
    {
      "start": 12.1,
      "end": 14.8,
      "text": "Your delivery is here."
    }
  ],
  "keywords": ["delivery"],
  "audio_events": ["knock"],
  "classification": "delivery_interaction",
  "confidence": 0.88,
  "summary": "Likely delivery interaction detected at the front door."
}
```

## Future Extensions

After the MVP, the idea can be extended in several useful directions.

### Multi-Room Deployment

Support multiple microphone nodes and route replay requests according to area, proximity, and trigger source.

### Additional Audio Event Understanding

Go beyond speech transcription:

- glass break
- crying
- yelling
- prolonged doorstep presence
- repeated knocking
- appliance alarms

### User Modeling

Over time, structured summaries can feed memory systems and help the assistant understand patterns:

- typical delivery times
- common visitor phrases
- preferred interaction style
- repeated household routines

### Risk-Aware Automation

The system should eventually distinguish between:

- harmless event
- useful reminder
- uncertain event
- suspicious event
- dangerous event

This enables safer AI behavior than blind automation.

### Edge Acceleration

Some lightweight preprocessing can move to low-power accelerators:

- VAD
- wake-word detection
- keyword spotting
- basic event classification

Heavier ASR and agent reasoning can remain on a stronger central machine.

## Open Technical Questions

These questions should remain visible as the project evolves.

- What audio format best balances replay quality and storage size?
- How large should the PC ring buffer be for each node by default?
- What packet loss and jitter handling is sufficient for the UDP audio uplink?
- How should replay requests be authenticated?
- How should room-level privacy policy be encoded?
- How should false positives be measured?
- Which audio events are worth classifying beyond speech?
- Should the replay be analyzed synchronously or through a task queue?
- How should memory entries derived from audio be validated before long-term retention?

## Practical Vision

The long-term value of this project is not just building another voice assistant.

The real value is building an event-aware perception layer for a home agent:

- selective rather than indiscriminate
- contextual rather than generic
- privacy-bounded rather than archival
- useful in real domestic situations

If implemented well, this system gives a home AI assistant a meaningful new capability: not permanent surveillance, but short-lived contextual hearing aligned with what is actually happening in the environment.
