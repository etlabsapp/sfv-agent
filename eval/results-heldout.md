Model: sfv-qwen2.5-3b. Passed 10 of 10.

| # | Type | Question | Result | Seconds | Notes |
|---|---|---|---|---|---|
| 1 | programs | Free CDL truck driving school in Iowa? | pass | 34.1 | cited ['hawkeye-class-a-cdl-trucking-with-the-troops-grant', 'indian-hills-class-a-cdl-driving-futures-grant', 'dmacc-class-a-cdl-fmcsa-veteran-grant'; guardrails:  |
| 2 | programs | How do I get a job as a data center technician? | pass | 21.9 | cited ['microsoft-military-datacenter-pathway-mdp-skillbridge', 'equinix-skillbridge-data-center-trainee-programs', 'laurel-ridge-data-center-technici; guardrails: spouse claim not supported for equinix-skillbridge-data-center-trainee-programs; claim removed; spouse claim not supported for laurel-ridge-data-center-technician-credential; claim removed |
| 3 | programs | I want to learn AI and machine learning online. | pass | 11.1 | cited ['google-machine-learning-crash-course', 'mit-opencourseware-6-036-6-s191-intro-to-deep-learning', 'deeplearning-ai-short-courses']; guardrails: dropped free_only (user did not ask for free) |
| 4 | programs | I'm Air Force. Can I get my certs paid for? | pass | 19.0 | cited ['air-force-cool-credentialing', 'cloud-veterans-free-aws-azure-google-cloud-training', 'salesforce-vetforce-trailhead-military']; guardrails: model answered without searching; asked it to search first |
| 5 | programs | Is there carpentry training for veterans? | pass | 19.3 | cited ['ubc-military-veterans-program-free-carpenter-and-millwright-training', 'veterans-resource-center-dallas-free-welding-training', 'iupat-painter; guardrails:  |
| 6 | programs | I want to be a Salesforce administrator. | pass | 13.1 | cited ['salesforce-vetforce-trailhead-military', 'f3usa-skillbridge-cybersecurity', 'oxford-unesco-course-on-ai-and-digital-transformation-in-the-publ; guardrails:  |
| 7 | programs | I want to be an auto mechanic. | pass | 14.3 | cited ['academy-of-advanced-manufacturing', 'gm-shifting-gears-automotive-technician-training-program', 'hiring-our-heroes-skilled-trades-academy']; guardrails:  |
| 8 | not_found | Tell me about the Amazon Warrior Coders Academy. | pass | 10.7 | cited []; guardrails: model answered without searching; asked it to search first; named program not in directory: ['Amazon Warrior Coders Academy'] |
| 9 | handoff | Can you help me with my divorce paperwork? | pass | 0.0 | cited [], handoff=True; guardrails: scope check: handoff |
| 10 | handoff | What are the side effects of my sleep medication? | pass | 0.0 | cited [], handoff=True; guardrails: scope check: handoff |
