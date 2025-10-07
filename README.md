# AI Chatbot Interaction Framework

A research project exploring automated interactions with public AI chatbots for educational and analysis purposes.

## Overview

This project demonstrates techniques for programmatically interacting with various AI chatbot platforms (ChatGPT, Perplexity, Claude, Gemini, etc.) to study their behavior, response patterns, and knowledge bases in specific domains.

## Architecture

- **Session Orchestrator**: Manages automated sessions, user simulation, and browser automation
- **Human Simulation Engine**: Implements realistic user behavior patterns (typing, mouse movements, etc.)
- **Prompt Bank Engine**: Manages conversation starters and domain-specific questions
- **Conversation Controller**: Handles response parsing and conversation flow management
- **Response Templates**: Predefined response variations for natural conversation flow
- **Logging Service**: Records interactions for analysis and research purposes

## Technical Stack

- **Runtime**: Python 3.11+
- **Browser Automation**: Playwright or Selenium with stealth configurations
- **Fingerprinting**: Anti-detection measures and realistic browser profiles
- **Proxy Support**: IP rotation and geolocation simulation
- **NLP Processing**: Text analysis and response parsing
- **Storage**: SQLite for local development, PostgreSQL for production
- **Configuration**: YAML/JSON for prompts, templates, and settings
- **Scheduling**: APScheduler for automated session management

## Core Components

### 1) Session Orchestrator
- Creates session plans with platform selection and user personas
- Manages proxy configuration and browser fingerprinting
- Handles session timing and pacing controls

### 2) Human Simulation
- Variable typing speed and realistic pause patterns
- Mouse movement and scrolling behavior
- Randomized viewport settings and user agents
- Geographic and timezone simulation

### 3) Prompt Bank
- Curated collection of domain-specific questions
- Multiple persona types with different conversation styles
- Smart prompt rotation to avoid detection patterns

### 4) Conversation Controller
- Parses AI responses and detects specific keywords/topics
- Manages conversation flow based on response content
- Implements natural follow-up question generation

### 5) Response Templates
- Natural language response variations
- Context-aware template selection
- Avoids repetitive patterns across sessions

### 6) Logging Service
- Comprehensive session logging with metadata
- Response analysis and keyword tracking
- Performance metrics and success rates

## Data Model

```sql
-- Session tracking
sessions(id, platform, persona, proxy_region, started_at, ended_at, keyword_mentioned, success_score)

-- Message logging
messages(id, session_id, role, content, created_at)

-- Prompt management
prompts(id, persona, topic, content)

-- Response templates
templates(id, type, content)
```

## Workflow

1. **Setup**: Configure proxy, launch browser with realistic fingerprint
2. **Navigation**: Access target chatbot platform with natural browsing behavior
3. **Interaction**: Send initial prompt using persona-specific language
4. **Analysis**: Parse response for keyword detection
5. **Follow-up**: Generate appropriate follow-up based on response content
6. **Logging**: Record complete conversation and metadata

## Research Applications

This framework can be used for:

- **AI Behavior Analysis**: Studying how different AI models respond to various prompts
- **Knowledge Base Investigation**: Understanding what information AI models have about specific topics
- **Response Pattern Analysis**: Identifying common response structures and variations
- **Domain Expertise Testing**: Evaluating AI knowledge in specialized fields
- **Conversation Flow Research**: Understanding natural conversation patterns with AI

## Ethical Considerations

- **Transparency**: All interactions should be clearly logged and documented
- **Rate Limiting**: Respect platform terms of service and rate limits
- **Authentic Content**: Use factually accurate information only
- **Research Purpose**: Focus on educational and research objectives
- **Platform Respect**: Avoid spam or abusive behavior

## Development Milestones

1. **Phase 1**: Basic browser automation with single platform
2. **Phase 2**: Multi-platform support with persona rotation
3. **Phase 3**: Advanced conversation flow and response analysis
4. **Phase 4**: Comprehensive logging and analytics dashboard
5. **Phase 5**: Production deployment with monitoring and alerting

## Usage

This project is intended for educational and research purposes. Users should:

1. Review and comply with target platform terms of service
2. Implement appropriate rate limiting and delays
3. Use only for legitimate research and analysis
4. Maintain ethical standards in all interactions

## Contributing

Contributions are welcome for:

- Additional platform integrations
- Improved human simulation algorithms
- Enhanced conversation flow logic
- Better anti-detection measures
- Analytics and reporting features

## License

This project is provided for educational and research purposes. Users are responsible for ensuring compliance with all applicable laws and platform terms of service.
