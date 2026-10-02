# Hackathon winning compass

This is the repository-adopted playbook. Workspace playbooks are reusable references; changes to them do not automatically change this project's rules.

Private source pointers are marked `BUILDER-ONLY REFERENCE`. They are not included in a teammate's clone. Follow the [reference rules](../docs/agents/domain.md#shared-documents-and-private-evidence). Source labels preserve provenance, not new verification.

**Purpose:** Turn a hackathon brief into a focused product, a complete build, and a short judge-ready demonstration.

**Primary source:** The supplied builders' Space transcript in `space.md`, BUILDER-ONLY REFERENCE `space.md`.

**Captured:** 2026-09-06. The transcript does not state the exact broadcast date.

**Use:** Read this before choosing a hackathon or generating ideas. Return to the phase checklist during the build. For any hackathon, use BUILDER-ONLY REFERENCE `playbooks/HACKATHON_COMPASS_SESSION_PROMPT.md` with that project's active workflow; this guide's historical examples do not impose their old gates or event-specific requirements.

This guide curates the methods shared by Dre, Daniel, Tim, Dave, and other speakers. It gives the greatest weight to Dre because he explained his process in the most detail. It separates direct transcript lessons from operational recommendations added during curation.

## Source and attribution

The transcription service split the Space into several blocks. It assigned generic speaker numbers that reset between blocks. The text also contains recognition errors such as "Web BCP" for WebMCP and "referral" for Refero.

Speaker attribution therefore uses conversational handoffs, self-introductions, project references, and public profile checks.

| Name used here | Identity | Confidence | Basis |
| --- | --- | --- | --- |
| Dre | `@dreyethh` | High | The host repeatedly hands the microphone to "Dre." The speaker discusses Erilog and his recent wins. |
| Daniel | Daniel Asaboro, `@DisturbedCoin` | High | Other speakers address the host as Daniel. He refers to Leash and his judging experience. |
| Tim | `@winsznx` | High | He introduces himself as Tim. His public GitHub profile uses the same name and hackathon background. |
| Davexinoh | `@dontfadedave`, co-host, developer, security researcher, and hackathon builder | High | The user confirms that Davexinoh was the Dave who co-hosted the Space. His public profile and repositories fit the technical discussion. |
| Other Dave | Unidentified participant | Low | The user recalls another Dave but not his username. The transcript does not provide a handle or a clean handoff that separates his advice from Davexinoh's. |
| Other speakers | Rex, Roland, Akiomi, Vic, Israel, Young, Seba, Imaya, Bonsai, Damien, Ima, Maxim, Solution, and Mori | Mixed | Their names appear in microphone handoffs, but the transcript does not provide stable handles for all of them. |

The user associates Dre with the Enoch208 and damishafe project set. The local repository research proves close collaboration across those accounts. It does not prove that all three public identities belong to one person. This guide attributes spoken statements to Dre and treats the portfolio connection as supporting context, not an identity claim.

### Speaker count and contribution audit

The working count is 19 speakers because the user confirms that co-host Davexinoh and another participant named Dave were different people. The transcript text alone supports only 18 named identities because it does not separate their turns reliably. The transcript service split the Space into five blocks and restarted labels such as `Speaker 1` in each block. Adding the five block totals would produce a false count.

Six identifiable people gave advice that can be reused as a hackathon method. A seventh may qualify if the early product critique came from the unidentified Dave rather than Davexinoh or Dre.

- Dre gave the deepest method for research, idea choice, execution, demos, and review.
- Daniel explained sponsor fit, personal problem knowledge, judging attention, and product continuation.
- Tim explained interface references, detailed design instructions, performance, and device testing.
- Davexinoh likely gave the late advice about learning the technical base instead of depending on generated code that the builder cannot inspect.
- Akiomi explained how to transfer a proven product pattern into another ecosystem when the sponsor makes that transfer useful.
- Vic explained how repeated builds, feedback, and revision shorten the path from beginner work to strong work.

Several other speakers improved the discussion through good questions, examples, or links. They helped expose the advice, but the transcript does not contain enough original method from them to count them as primary sources. These include Rex, Roland, Young, Seba, Imaya, Bonsai, Damien, Ima, Maxim, and Solution. Israel made a brief interjection. Mori joined near the end and said he had missed most of the discussion.

The current count treats Rex, Res, and Red as one person; Seba, Saba, and Siva as one person; Imaya and Omour as one person; Ima and Emma as one person; Maxim and Magazine as one person; Bonsai and Jerry X as one person; and Small and Mori as one person. Those variations appear to be transcription errors or a mix of display names and spoken names. It treats co-host Davexinoh and the unidentified Dave as separate people.

Identity references:

- [Dre on X](https://x.com/dreyethh)
- [Daniel on X](https://x.com/DisturbedCoin)
- [Tim on GitHub](https://github.com/winsznx)
- [Davexinoh on X](https://x.com/dontfadedave)
- [Davexinoh on GitHub](https://github.com/Davexinoh)
- Local Enoch208 and damishafe source registry, BUILDER-ONLY REFERENCE `docs/research/ENOCH_DAMISHAFE_SOURCE_REGISTRY.md`

Public profiles last checked on 2026-09-06.

## The central lesson

The advantage is not a secret prompt, MCP server, skill, or coding agent.

The advantage comes from five decisions made before and around the code:

1. Choose a contest that deserves your effort.
2. Understand what the sponsor and judges want to make possible.
3. Start from a problem you understand, not an idea generated from the brief by AI.
4. Define one user job and finish that job completely.
5. Design the demonstration while framing the product.

Dre said that a person could inspect his repositories for days and still miss the method. He then explained that he spends hours studying projects, judges, and past hackathons before he chooses his angle. `space.md`, line 263, BUILDER-ONLY REFERENCE `space.md#L263`

Daniel made the same point from another direction. More tools only consume more tokens when the underlying idea does not fit the contest. `space.md`, line 253, BUILDER-ONLY REFERENCE `space.md#L253`

## Dre's method in one page

This is the shortest faithful version of Dre's process.

### 1. Frame the idea

Answer three questions:

1. Who exactly is this for?
2. What complete job does it do?
3. What does the finished product look like?

"Busy parents" is too broad. A parent who must track a child's bedtime against a specific routine is concrete enough to shape the product. Specificity gives both the builder and the coding agent useful context. `space.md`, line 144, BUILDER-ONLY REFERENCE `space.md#L144`

### 2. Check the contest fit

Ask why the sponsor is paying people to build. The product must advance that goal. A generally useful savings journal was still a poor WebMCP entry because WebMCP did little essential work in the proposed loop. `space.md`, lines 174–186, BUILDER-ONLY REFERENCE `space.md#L174`

### 3. Study the people behind the brief

Dre spends about three to four hours studying the sponsor's projects, the judges, and prior hackathons. In one example, he read several judges' public posts as far back as six months. He found a shared interest in disaster response and used it to frame Erilog for humanitarian field workers who lose connectivity. `space.md`, line 263, BUILDER-ONLY REFERENCE `space.md#L263`

### 4. Explain it in one sentence

If the builder needs a chain of features to make the idea sound useful, the idea is not ready. Dre used a codebase assistant as an example because its user, problem, input, and result could be explained immediately. `space.md`, lines 188–190, BUILDER-ONLY REFERENCE `space.md#L188`

### 5. Let another person challenge it

Dre shares ideas with friends even when he already likes them. The purpose is not to ask permission. It is to learn whether another person can understand the product and see missing parts. `space.md`, line 144, BUILDER-ONLY REFERENCE `space.md#L144`

### 6. Use AI after the idea is clear

Dre described his build sequence as:

```text
idea
-> prompting
-> debugging
-> database, authentication, backend, and product work
-> deployment
-> demo video
```

`space.md`, lines 297–305, BUILDER-ONLY REFERENCE `space.md#L297`

AI helps express and implement a product the builder already understands. AI should not own the first act of deciding what human problem matters.

### 7. Finish the job

The product must solve its chosen problem completely before optional features receive attention. Completeness comes from the working user path, not from the number of features. `space.md`, lines 144–146, BUILDER-ONLY REFERENCE `space.md#L144`

### 8. Test against the field

After submitting, Dre reviews other entries and compares them with his product. He also asks several AI models to rank the products. He uses agreement across those reviews as a confidence check, not as the official result. `space.md`, lines 393–395, BUILDER-ONLY REFERENCE `space.md#L393`

### 9. Make the demo shorter than the limit

If the limit is five minutes, Dre does not submit a five-minute video. His target is short, precise, and easy to follow. The video uses a hook, a compact feature explanation, a visible product test, and a strong ending. `space.md`, lines 307–309, BUILDER-ONLY REFERENCE `space.md#L307` `space.md`, lines 385–395, BUILDER-ONLY REFERENCE `space.md#L385`

### 10. Learn after the result

When Dre loses, he asks judges for their criteria and feedback. Some reply and some do not. He uses the answer to improve the next product. `space.md`, line 395, BUILDER-ONLY REFERENCE `space.md#L395`

## Daniel's contribution

Daniel acted as the host, critic, and occasional judge. His advice focused on product ownership and judge attention.

### Start from your own advantage

Daniel argued that a builder should begin with work and problems they know. A content marketer should first inspect content and marketing failures. A developer should inspect development failures. Personal experience gives the builder details that a generic idea prompt cannot supply. `space.md`, lines 196–198, BUILDER-ONLY REFERENCE `space.md#L196`

### Use AI after human problem selection

When many teams give the same brief to the same models, their ideas and even their names converge. Those teams force judges to compare several similar products. Daniel's answer was to form the initial problem from experience, then use AI to shape or implement it. `space.md`, lines 196–198, BUILDER-ONLY REFERENCE `space.md#L196`

### Read the sponsor's motive

Daniel challenged the savings-journal submission because it did not advance WebMCP's stated purpose. His test asked whether the product demonstrated what the sponsor wanted to make possible. Installing the sponsor tool was insufficient. `space.md`, lines 174–186, BUILDER-ONLY REFERENCE `space.md#L174`

### Treat explanation as a design test

Daniel connected idea ownership with demonstration quality. If a builder did not form and understand the idea, the builder will struggle to explain it within three minutes. A technically working product can still lose at the first judging contact because its story is unclear. `space.md`, line 196, BUILDER-ONLY REFERENCE `space.md#L196`

### Tools amplify the idea

Skills, MCP servers, prompt libraries, and coding agents provide context and execution help. They cannot make a sponsor-misaligned product competitive. Daniel treated fascination with the tool stack as a distraction before idea fit is settled. `space.md`, line 253, BUILDER-ONLY REFERENCE `space.md#L253`

### Judge competition relative to your position

Entry count matters, but it is not the complete decision. Ask when you discovered the event, whether you can catch up, whether you have a stronger angle, and whether you can execute it. `space.md`, lines 337–343, BUILDER-ONLY REFERENCE `space.md#L337`

### Use design references as seeds

Daniel described starting Leash's visual identity from a newsletter screenshot. He used its newspaper feeling as a direction, then refined it into a distinct application. The lesson is to start with a concrete visual reference and transform it. `space.md`, line 421, BUILDER-ONLY REFERENCE `space.md#L421`

### Respect judge time

Daniel prefers submitting below the video limit. He argued that a tired reviewer is more likely to begin with a shorter entry and may stop searching after finding a convincing one. `space.md`, line 529, BUILDER-ONLY REFERENCE `space.md#L529`

### Use hackathons as product tests

Daniel relayed Tim's launchpad principle. Each hackathon tests an idea, execution method, or market. Continue when the result uncovers support or a larger opportunity. Move on when it does not. `space.md`, line 409, BUILDER-ONLY REFERENCE `space.md#L409`

## Tim's contribution

Tim, `@winsznx`, concentrated on visual execution, performance, and repeated building.

### Build repeatedly until one product earns continued attention

Tim introduced himself as someone who keeps building products until one works at a much larger level. Daniel later credited him with the view that hackathons are launchpads rather than products a builder must keep forever. `space.md`, line 80, BUILDER-ONLY REFERENCE `space.md#L80` `space.md`, line 409, BUILDER-ONLY REFERENCE `space.md#L409`

### Develop visual taste before prompting

A detailed prompt only works when the builder can describe the desired result. Tim advised learning enough design language to specify the navigation, hero, typography, sections, and component treatment. A generic landing-page request produces a generic box-heavy page. `space.md`, line 513, BUILDER-ONLY REFERENCE `space.md#L513`

### Use real product references

Tim recommended Refero, Dribbble, Figma, Spline, and designs published on X. A builder can give an agent a reference image or a `DESIGN.md`, then ask it to apply those rules to the new product's brand and workflow. The reference supplies constraints. It is not a page to copy unchanged. `space.md`, line 513, BUILDER-ONLY REFERENCE `space.md#L513`

### Iterate past the first generated design

The first output is a draft. Tim tells the agent which parts remain wrong and continues until the application fits his intended design. A single prompt can work only when it contains enough detail to control the result. `space.md`, line 513, BUILDER-ONLY REFERENCE `space.md#L513`

### Design the working application

A polished landing page cannot compensate for a weak dashboard or missing function. Tim told builders to make the working interface understandable to judges who may not know crypto. `space.md`, line 513, BUILDER-ONLY REFERENCE `space.md#L513`

### Design for bad conditions

Tim advised testing mobile, tablet, and desktop layouts. He also advised optimizing media and initial loading for weak networks. Text and controls should appear before nonessential media when possible. `space.md`, line 515, BUILDER-ONLY REFERENCE `space.md#L515`

### Prefer clarity and speed over spectacle

Long animations and heavy hero media can delay the judge without helping the product claim. A simple, coherent interface that loads and works is enough. `space.md`, line 515, BUILDER-ONLY REFERENCE `space.md#L515`

## Davexinoh's contribution and the second-Dave uncertainty

Davexinoh, `@dontfadedave`, is a developer and security-focused hackathon builder. His public profile names PlayWorldXI and Vouch, and his GitHub account contains 41 public repositories. This makes the late smart-contract answer consistent with his background. It does not prove the voice assignment. The automatic transcript does not attach handles to turns.

### Demand a precise problem and a real edge

After Rex described a spending journal, a critic asked what exact problem it solved, why existing journal products were insufficient, and whether WebMCP did anything essential beyond scanning a statement. The restart recap identifies that critic as either Dave or Dre. With two possible Daves, the transcript cannot identify which person delivered it. The test itself is strong: name the unsolved problem, the existing substitute, your difference, and the sponsor technology's necessary job. `space.md`, lines 102–114, BUILDER-ONLY REFERENCE `space.md#L102`

### Learn enough to inspect generated code

Near the end, Daniel calls on Dave and the next respondent advises a new smart-contract developer to choose a chain, study its language properly, write real code, and use available ecosystem support. Davexinoh's public security and development work makes him the likelier source, but this remains an inference. The durable lesson is to learn enough of the technical base to inspect and repair what an AI coding tool generates. The transcript's specific comparisons between programming languages are imprecise and should not be repeated as technical facts. `space.md`, lines 491–503, BUILDER-ONLY REFERENCE `space.md#L491`

### Help the room do the work

Daniel thanks Dave for co-hosting, handling the Space controls, and listening. The user confirms that this co-host was Davexinoh. That work helped turn a loose conversation into live product criticism. `space.md`, line 529, BUILDER-ONLY REFERENCE `space.md#L529`

## Phase 0: choose the right contest

Hackathon selection is part of product strategy.

### Dre's portfolio rule

Dre bookmarks many events but enters only a few. He gave an example of bookmarking ten and building for three. He expects to put full effort into each selected product. `space.md`, lines 343–345, BUILDER-ONLY REFERENCE `space.md#L343`

A large field is not an automatic reason to withdraw. Dre cited wins or placements in events with more than 1,000 and nearly 3,000 participants. The real question is whether you have enough time, skill, and product quality to compete. `space.md`, line 343, BUILDER-ONLY REFERENCE `space.md#L343`

For a new builder, a smaller field can be useful. More entries receive human attention, and the builder gets a better chance to finish, receive feedback, and learn. `space.md`, lines 218 and 345, BUILDER-ONLY REFERENCE `space.md#L218`

### Entry decision

Score each item from 0 to 2.

| Question | 0 | 1 | 2 |
| --- | --- | --- | --- |
| Problem access | No relevant experience | Can interview or study users | Has lived the problem |
| Sponsor fit | Sponsor is decorative | Sponsor improves the product | Product depends on sponsor capability |
| Time | Starting too late | Tight but possible | Enough time for build and demo |
| Field | Many strong similar entries | Some room | Clear room or unusual angle |
| Proof | Mostly claims | Some visible evidence | Main result is easy to test |
| Delivery | Several unknown systems | One large unknown | Main path uses known tools |
| Motivation | Prize only | Learning plus prize | Would value the product or skill anyway |

Use the score to expose weak conditions. Do not convert it into a fake probability of winning.

### Entry gate

Enter when all four statements are true:

- You can state the sponsor's purpose in plain language.
- You have one credible problem source.
- You can show the main result within the video limit.
- You can finish one complete path before the deadline.

## Phase 1: read the room

Daniel's recurring question was: what are the organizers trying to push?

A hackathon sponsor is spending money to cause a type of product, usage, proof, or attention. Reading only the submission checklist misses that intent. `space.md`, lines 174–186, BUILDER-ONLY REFERENCE `space.md#L174`

### Research order

1. Read the rules and rubric.
2. Use the sponsor's product.
3. Read the current documentation.
4. Study prior winners and rejected patterns.
5. Review each judge's public professional interests.
6. Review the sponsor's recent launches and stated goals.
7. Compare the brief with what the ecosystem currently lacks.

### Three-to-four-hour research sheet

```text
Sponsor:
Sponsor's main product:
Capability the sponsor wants builders to use:
Behavior that proves real use:
Common weak integration:

Judge 1 professional interests:
Judge 2 professional interests:
Judge 3 professional interests:
Theme shared by two or more judges:

Past winning product pattern:
Crowded product pattern:
Underused user or workflow:

One real-world problem that fits:
Why this sponsor changes the solution:
What the judge can see in under three minutes:
```

### Ethical boundary

Use public professional statements to understand priorities. Do not treat one casual post as a hidden scoring rule. The official rubric remains the authority. A judge-interest theme strengthens a product only when the product also solves a real problem and fits the brief.

## Phase 2: generate ideas from experience

Daniel warned that asking the same AI systems to generate ideas from the same brief causes convergence. Builders receive similar assistants, bots, names, and feature lists. They then compete inside the same crowded category. `space.md`, lines 196–198, BUILDER-ONLY REFERENCE `space.md#L196`

His alternative is founder fit. Start with work, industries, users, and failures you know. A content marketer can see problems that a developer without that experience will not see, no matter how long the developer prompts an AI system. `space.md`, line 196, BUILDER-ONLY REFERENCE `space.md#L196`

Dre later gave the same warning through the "smart money bot" example. A generic prompt produces the same Telegram trading bot for many teams. The builder must ask what they would personally need and add the missing moment from experience. `space.md`, lines 449–457, BUILDER-ONLY REFERENCE `space.md#L449`

### Human-first problem inventory

Before opening an idea-generation model, aim to write at least five events from memory. The source and exception rule below applies when five genuine events are unavailable:

- A task you repeat and dislike.
- A mistake that cost time or money.
- A handoff where information disappeared.
- A product that forces an awkward workaround.
- A job where connectivity, trust, cost, privacy, or proof fails.
- A problem a colleague repeatedly complains about.
- A situation where a sponsor capability would change the result.

Write events, not categories.

Weak:

```text
Personal finance is difficult.
```

Stronger:

```text
A freelance designer receives income through three accounts and cannot tell
which client invoices remain unpaid before accepting the next job.
```

### Cross-ecosystem transfer

Akiomi described another valid source of ideas. Find a useful product in another ecosystem, then ask whether the current sponsor makes it possible or meaningfully better here. He said this method helped him place second in an earlier event. `space.md`, line 230, BUILDER-ONLY REFERENCE `space.md#L230`

This is adaptation, not copying. Change the user problem, constraint, mechanism, or proof. Check the source license and the hackathon's prior-work rules.

### Keep the problem's source visible

The five-event inventory prevents a generic AI-generated shortlist. It is our working safeguard, not a claim that Dre writes five personal incidents before every event.

A problem lead may come from the builder's experience, a direct user report, an official sponsor brief, a time-sensitive change, or a failure observed in an existing tool. Record the source beside the lead. A sponsor brief shows what the sponsor wants built; it does not prove that users want it. A judge's public interests may suggest a setting, but they do not establish a hidden judging rule or a user problem.

If the builder cannot supply five genuine incidents, record the actual count. Do not invent the rest. A sponsor-led idea may still be considered with the builder's explicit approval, but later validation must check the user problem and leave missing demand evidence visible.

## Phase 3: frame the product

Framing is where the idea becomes buildable.

### The three questions

```text
Who exactly is it for?
What complete job does it do?
What does finished look like?
```

### Complete idea card

```text
Product name:

Exact user:
Triggering moment:
Current failed process:
Cost or consequence:

Complete job:
User input:
Product action:
Visible result:

Sponsor capability:
Why it is necessary:

Definition of finished:
Smallest complete path:
Excluded features:

One-sentence explanation:
One-minute spoken explanation:
Three-minute demonstration:
```

### One-sentence formula

```text
For [specific user] during [specific moment], [product] uses [necessary
sponsor capability] to turn [input or failed state] into [completed result].
```

The sentence is a test. It is not the final marketing copy.

### Articulation test

Explain the idea aloud without reading notes.

Pass when a listener can answer:

- Who uses it?
- What goes wrong today?
- What does the product do?
- Why does the sponsor matter?
- What will the demo prove?

Dre connected poor articulation directly to poor demos. If the builder cannot explain the product before coding, the video will become a feature tour that judges cannot follow. `space.md`, lines 188–190, BUILDER-ONLY REFERENCE `space.md#L188`

## Phase 4: challenge the idea before building

Use people before using more prompts.

### Internal extension: After It Works

This extension is an internal project method inferred from later portfolio analysis. The Space does not state that Dre uses this named framework. Do not attribute it to him or treat another builder's portfolio as user evidence.

Use the extension after the builder has a sourced problem and a relevant sponsor capability:

```text
Sourced problem
-> relevant capability
-> assume the capability works
-> what still fails or becomes newly important?
-> what decision or control is missing?
-> what is the smallest mechanism that changes the result?
-> what visible same-case contrast can a judge inspect?
```

The downstream failure can be supported evidence, a direct inference, or an unsupported hypothesis. Keep those categories separate. Do not reward a familiar trust, permission, provenance, or verification pattern unless it follows from the specific user and job.

The current Monad session prompt uses this extension when it helps challenge a problem/capability pair or selected product. It is optional and supplies no minimum match or candidate count. Demand and substitute evidence remain separate validation questions.

Ask two experienced builders or target users to listen to the one-minute explanation. Do not first teach them the product. Ask them to repeat the idea in their own words.

### Challenge questions

1. Which user is this for?
2. What exact problem does it solve?
3. Does the sponsor perform essential work?
4. Which feature can we remove?
5. What makes this different from the first obvious AI idea?
6. What must work for the demo to succeed?
7. What part sounds invented or unsupported?
8. Would the product still make sense after the event?

### Stop conditions

Reframe the idea when:

- The explanation needs several unrelated features.
- The sponsor appears only in one side feature.
- The user is a broad population.
- The finished state is "a dashboard" rather than a completed job.
- The builder cannot describe the main video moment.
- The idea came entirely from a generic AI response.

## Phase 5: prompt AI after the product is understood

The Space did not reveal one secret master prompt. Dre's disclosed method is more useful: decide the idea, then prompt, debug, complete the product, deploy, and record.

### Build brief for an AI coding agent

```text
Build this product:
[one-sentence explanation]

User:
[one specific role]

Trigger:
[one moment]

Complete job:
[one result the user must reach]

Required sponsor behavior:
[real operation and visible proof]

P0 user path:
1. [input]
2. [product action]
3. [sponsor operation]
4. [visible result]
5. [proof or failure state]

Definition of done:
[observable completion conditions]

Non-goals:
[features excluded from this build]

Design reference:
[image, URL, or DESIGN.md]

Demo contract:
[exact action and result the video will show]

First task:
Implement the smallest vertical path. Stop after its checks pass and report
what remains unproved.
```

This template is an operational synthesis. No speaker dictated it word for word.

### Good uses of AI

- Turn a settled idea into a build plan.
- Find missing states or failure cases.
- Implement a narrow path.
- Debug concrete failures.
- Generate test data.
- Compare a product against a published rubric.
- Improve a demo script after the product works.

### Weak uses of AI

- Asking for "ten winning ideas" before supplying lived problems.
- Accepting the first generated product name and category.
- Adding features until an unclear idea sounds substantial.
- Asking tools to compensate for missing sponsor fit.
- Treating one model's ranking as proof of likely placement.

## Phase 6: prototype the dangerous claim

The Space did not include a detailed prototype recipe. It established two useful constraints:

- The product must complete one job before optional work starts.
- The demonstration must visibly test the product.

The following loop applies those constraints without inventing a secret method.

### Prototype loop

1. Name the claim that would make the product worthless if false.
2. Create one realistic input that contains the target problem.
3. Connect the real sponsor capability.
4. Run the shortest path from input to user result.
5. Save the output or proof.
6. Run one failure case.
7. Show the result to one person who did not build it.
8. Continue only when the claim is visible without a long explanation.

### Prototype completion gate

The prototype passes when:

- The real sponsor operation runs.
- The user receives a useful result.
- The main failure appears when the sponsor capability is absent or fails.
- A viewer understands the difference.
- The proof can appear in the demo.

If the promise is faster, cheaper, higher quality, or worth paying for, compare it with the alternative on the same task and input. Freeze the scope, success measure, full time boundary, and costs before running either path. Report mismatches instead of claiming a win from unequal tests. A working prototype proves that a path works; it does not by itself prove superiority or demand.

Do not build a landing page to hide a missing prototype.

## Phase 7: turn the prototype into a complete product

Completeness does not mean many features. It means the chosen user can finish the promised job.

### Completion path

```text
open product
-> understand next action
-> provide input
-> run core operation
-> receive result
-> inspect proof or status
-> recover from the main failure
```

### Build order

1. Finish the central user path.
2. Add the minimum data storage.
3. Add authentication only when the job needs identity.
4. Add the minimum backend or contract work.
5. Handle the main failure state.
6. Add proof that judges can inspect.
7. Deploy early.
8. Run the deployed path under demo conditions.
9. Add visual polish after the path is stable.

Dre listed database, authentication, backend work, deployment, and the demo after ideation, prompting, and debugging. The sequence supports a product, not a disconnected technical experiment. `space.md`, line 305, BUILDER-ONLY REFERENCE `space.md#L305`

## Phase 8: design with references

Tim described two design methods.

### Method A: direct the model in detail

The builder must have a visual opinion. Specify the navigation, hero, typography, sections, layout, and component behavior. "Build a landing page" produces the same box-heavy result for many builders. `space.md`, line 513, BUILDER-ONLY REFERENCE `space.md#L513`

### Method B: adapt real references

Use real interfaces from:

- [Refero](https://refero.design/)
- [Refero DESIGN.md examples](https://styles.refero.design/)
- [Dribbble](https://dribbble.com/)
- [Figma Community](https://www.figma.com/community)
- [Spline Community](https://spline.design/)
- designers who publish work on X

Extract the useful visual rules. Adapt them to the product. Do not reproduce another product unchanged.

Daniel described using a newsletter screenshot as the seed for Leash's newspaper-like visual identity. He and the coding model then refined that idea across the application. `space.md`, line 421, BUILDER-ONLY REFERENCE `space.md#L421`

### Design brief

```text
Visual reference:
Product mood:
Typography:
Color rules:
Spacing rules:
Navigation:
Primary screen:
Main user action:
Proof or result area:
Mobile behavior:
Loading behavior:
Elements to avoid:
```

### Tim's product UI rules

- The dashboard matters more than a beautiful landing page with no working product.
- The interface should help non-crypto judges understand a crypto product.
- Test mobile, tablet, and desktop navigation.
- Optimize for a poor connection.
- Use WebP for images and WebM for video when browser support fits the build.
- Load useful text and controls before heavy media.
- Prefer clear screens over long decorative animation.
- Ask the coding agent for revisions until the result matches the design brief.

`space.md`, lines 513–515, BUILDER-ONLY REFERENCE `space.md#L513`

## Phase 9: test completeness

Dre's CKB account illustrates his meaning of completeness. The product was not merely novel within its track. The whole submitted result was strong enough for judges to rank it across three tracks. `space.md`, lines 389–395, BUILDER-ONLY REFERENCE `space.md#L389`

### Product test

- Can a new visitor identify the user and job from the first screen?
- Can the visitor complete the main path without builder help?
- Does the sponsor integration run for real?
- Does the important result appear in the interface?
- Does the main failure have a useful state?
- Does the deployed build load on a modest connection?
- Does the repository explain how to reproduce the proof?
- Does the demo use the same product and result?

### Competitor rehearsal

Dre compares his product with the visible field and asks several models for independent rankings. Use this as a red-team exercise:

1. Freeze the official rubric.
2. Give each model the same candidate set and evidence.
3. Require criterion-by-criterion reasons.
4. Record disagreements.
5. Repair the weakest supported criterion.
6. Keep uncertain scores uncertain.

AI evaluation can expose unclear claims. It cannot predict private judging or guarantee a placement.

## Phase 10: make the demo a judging tool

The demo is often the first and sometimes the only artifact a judge studies closely. Daniel and several audience members returned to this point throughout the Space. `space.md`, lines 196 and 369–383, BUILDER-ONLY REFERENCE `space.md#L369`

### Dre's disclosed timing

- Introduction: about 10 to 20 seconds.
- Feature explanation: about 20 seconds.
- Visible product testing: about 30 to 40 seconds.
- Remaining time: the rest of the main path, proof, and conclusion.
- Opening: a strong hook.
- Ending: a strong final impression.

`space.md`, lines 385–395, BUILDER-ONLY REFERENCE `space.md#L385`

The transcript's remaining-time wording is unclear. The schedule below turns the principle into a complete three-minute plan.

### Curated three-minute demo

| Time | Job |
| --- | --- |
| 0:00–0:15 | Name the user, failure, and consequence. |
| 0:15–0:35 | State the product promise and sponsor's necessary role. |
| 0:35–1:25 | Run the main user path with real input. |
| 1:25–1:55 | Show the sponsor operation and resulting state. |
| 1:55–2:20 | Show the proof or important failure contrast. |
| 2:20–2:40 | State the completed user result. |
| 2:40–2:55 | Close with the memorable difference and current limits. |
| 2:55–3:00 | Leave a small safety margin. |

### Recording choices

Dre uses different methods based on the product and available time:

- direct Mac screen recording;
- screen recording followed by a voice-over for technical products;
- Remotion or another code-based video method when useful.

The method is secondary. Clarity and visible testing matter more than cinematic production. `space.md`, line 309, BUILDER-ONLY REFERENCE `space.md#L309`

### Demo rules

- Submit below the maximum duration.
- Demonstrate the product. Do not narrate screens that never act.
- Show the core result early.
- Give the longest uninterrupted segment to the main user path.
- Remove filler words and long setup.
- Record the deployed build when possible.
- Keep a local or replayable proof for network failure.
- End with the user result, not a feature list.

Daniel explained the attention advantage of a three-minute submission when most competitors use the full five-minute limit. `space.md`, line 529, BUILDER-ONLY REFERENCE `space.md#L529`

## Phase 11: submit like the judge is tired

Assume the judge has many entries and limited time.

Put these items first:

1. Demo video.
2. One-sentence product statement.
3. Live product.
4. One-command or one-page verification path.
5. Main proof.
6. Setup and architecture.
7. Honest limitations.

A single clear page can outperform a series of weak artifacts. Daniel described a bounty where one concise page persuaded the reviewer. `space.md`, line 529, BUILDER-ONLY REFERENCE `space.md#L529`

### Final submission check

- Every required field is complete.
- Every sponsor claim points to real behavior.
- The public repository runs from clean instructions.
- The video is below the limit.
- The first 20 seconds explain the problem.
- The product test is visible.
- Heavy media does not block the first screen.
- Prior work and borrowed design references are disclosed.
- The public post uses the same product claim as the demo.

## Phase 12: treat the result as data

Several speakers described hackathons as a learning loop, not a sequence of isolated bets.

### After a loss

1. Ask judges for the rubric breakdown and direct feedback.
2. Compare the feedback with your pre-submission forecast.
3. Find the earliest wrong decision.
4. Record whether the failure came from selection, framing, implementation, proof, or presentation.
5. Change one part of the process before the next event.

Vic argued that builders should reduce the time between being inexperienced and becoming good. Frequent builds help only when each result changes the next attempt. `space.md`, lines 238–251, BUILDER-ONLY REFERENCE `space.md#L238`

### After a win

Dre advised builders to ask about grants, developer programs, founder support, and continued product work. He continues products that show potential, but he does not try to maintain every project. `space.md`, line 405, BUILDER-ONLY REFERENCE `space.md#L405`

Daniel relayed Tim's useful framing: treat a hackathon as a launchpad for an idea. Do not become attached to every build. Continue the product when the event uncovers real support, users, or a larger opportunity. `space.md`, line 409, BUILDER-ONLY REFERENCE `space.md#L409`

### Post-hackathon record

```text
Hackathon:
Product:
Result:

What judges praised:
What judges rejected or missed:
What users understood immediately:
What required explanation:

Strongest product decision:
Earliest wrong decision:
Technical failure:
Demo failure:

Continue, reuse, archive, or stop:
Reason:
One process change for the next event:
```

## Advice from other speakers

### Akiomi: transfer a proven pattern across ecosystems

Study what works elsewhere. Bring it into the sponsor's ecosystem only when the sponsor adds a meaningful new capability or constraint. Adapt the product and respect prior-work and license rules. `space.md`, line 230, BUILDER-ONLY REFERENCE `space.md#L230`

### Vic: optimize for skill growth

Prize money is an outcome of strong work, not a substitute for developing the skill. Build, request feedback, apply it, and shorten the learning cycle. `space.md`, lines 238–251, BUILDER-ONLY REFERENCE `space.md#L238`

### Audience consensus: the demo is part of the product

Several speakers estimated that judges may spend most of their attention on the demo because they cannot deeply inspect thousands of repositories. The percentage claims were personal estimates, but the operational lesson is sound: make the product understandable and testable inside the video limit. `space.md`, lines 369–383, BUILDER-ONLY REFERENCE `space.md#L369`

### Community practice

The host used a live one-minute idea exercise so listeners had to apply the lesson instead of only hearing it. A builder stated the user, problem, and intended product. The group then challenged sponsor fit and clarity. `space.md`, lines 90 and 132–154, BUILDER-ONLY REFERENCE `space.md#L90`

Use the same exercise with a team:

1. Read the brief.
2. Take one minute to form an idea.
3. Pitch it in one minute.
4. Let others repeat what they understood.
5. Identify the first missing link.

## Claims to treat carefully

The Space included useful heuristics and some statements that should not become universal rules.

### Judge research is a signal, not the rubric

Studying public interests can reveal language, use cases, and concerns that resonate. It cannot replace compliance with the official rules or evidence that the problem is real.

### A large field is not automatically bad

Dre gave both sides. New builders may learn faster in smaller contests. Strong builders can still win crowded global events when they start early and have a strong product.

### A loss does not prove the product has no value

Daniel described a loss as a sponsor signal about value. Dre separately said that losing does not invalidate a product that solves a real problem. The safe interpretation is: a result is evidence about this event and panel, not final market truth.

### AI ranking is not judge validation

Agreement among several models can expose obvious weaknesses. Models may share blind spots and cannot see private judging discussions.

### Cross-ecosystem inspiration is not permission to copy

Reuse a problem pattern or interaction principle. Preserve attribution. Follow the license. Meet the event's original-work rules.

### Design polish cannot rescue a broken job

Tim was explicit that a beautiful landing page can still front a bad product. Function, loading speed, dashboard clarity, and responsiveness remain part of the design.

### Technical learning claims need independent checks

One speaker described Solidity as a JavaScript framework. That is technically incorrect. Solidity is a separate smart-contract programming language. The useful underlying lesson is to build genuine technical skill and practice while learning.

## The reusable operating checklist

### Before entering

- [ ] I know why the sponsor is funding the event.
- [ ] I can compete with the time and skills available.
- [ ] I have one real problem source.
- [ ] I can show a complete result within the video limit.

### Before selecting the idea

- [ ] The raw problem came from experience, observation, or direct evidence.
- [ ] I named one exact user.
- [ ] I named one triggering moment.
- [ ] The product finishes one job.
- [ ] The sponsor performs necessary work.
- [ ] I can explain the idea in one sentence and one minute.
- [ ] Another person can repeat the idea accurately.
- [ ] The idea is not the first generic answer from AI.

### Before building the full product

- [ ] The dangerous claim passed a small real test.
- [ ] The sponsor integration ran for real.
- [ ] The result is visible and saved.
- [ ] One failure case is known.
- [ ] P0 excludes optional features.

### Before recording

- [ ] The deployed main path works.
- [ ] The first screen loads quickly.
- [ ] Mobile, tablet, and desktop layouts are usable where required.
- [ ] The video script begins with the user problem.
- [ ] The main test receives the most screen time.
- [ ] The ending states the completed outcome.
- [ ] The recording is shorter than the allowed maximum.

### After judging

- [ ] I requested feedback.
- [ ] I recorded the earliest wrong decision.
- [ ] I chose continue, reuse, archive, or stop.
- [ ] I changed one part of my next process.

## Immediate implications for the Sibyl hackathon

This is a historical example from another event. For a new hackathon, use the general method above with BUILDER-ONLY REFERENCE `playbooks/HACKATHON_COMPASS_SESSION_PROMPT.md`, that project's active workflow and current official rules; do not carry Sibyl's product requirements or candidate counts into another entry.

The Space changes one part of the current Step 5 plan.

The fresh idea-selection agent should not invent all three candidates from the hackathon brief. That repeats the AI-convergence mistake described by Daniel and Dre.

Use this order:

1. The builder supplies at least five real memory failures from personal work, observed users, or existing direct research.
2. The agent checks each failure against Sibyl's capabilities and the official rubric.
3. The agent shapes exactly three product candidates.
4. The builder explains each candidate aloud in no more than one minute.
5. A candidate survives only when its user, job, Sibyl role, changed action, and deletion effect remain clear.
6. The builder selects one candidate.
7. A fresh session builds the smallest visible memory path that day.

The existing research already covers Sibyl, the judges, current competitors, and participant patterns. Dre's three-to-four-hour research lesson does not justify another broad search. This project has exceeded that research budget. The useful move now is to add the builder's lived problem inventory, select the strongest fit, and build.

For Sibyl, the one-sentence test is:

```text
For [specific user] during [repeated job], [named agent] learns [changing
outcomes] across fresh sessions and uses them to change [visible later action].
Deleting Sibyl removes or materially weakens that adaptation.
```

The product still needs one complete job, a working deployed path, and a demonstration shorter than the allowed maximum.

## Final compass

When the project becomes confusing, return to these questions:

```text
Is this contest worth our best effort?
What is the sponsor paying builders to make possible?
Who exactly has the problem?
What complete job must the product finish?
Why is the sponsor capability necessary?
Can another person understand the idea in one minute?
What is the smallest test of the dangerous claim?
Can the deployed product complete the job?
Can a tired judge see the result in under three minutes?
What will this result teach us before the next build?
```

If an answer is unclear, fix that layer before adding features below it.
