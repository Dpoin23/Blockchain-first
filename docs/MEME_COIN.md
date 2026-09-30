# Meme coin: name, shape, and what to decide first

A meme coin is a token people trade because of a joke, a picture, or a crowd. Most of them go to zero. This document is a way to choose a name and a contract shape you can explain in public. It is not a promise of price, and it is not legal or financial advice. How you market a token can create legal duties that depend on where you and your buyers live. If you plan to take anyone else's money, talk to a lawyer before you deploy.

The learning chain in this repo is the wrong home for that token. Its proof of work is capped so a laptop can rewrite history. A public meme coin lives on a network people already use. The reference contract is an EVM ERC-20, which fits Ethereum and Base (including their testnets). Solana is a common home too, and it needs a different program than `contracts/FixedSupplyToken.sol`. Pick one network in [DEPLOYMENT.md](DEPLOYMENT.md) phase 3 and stay there for the testnet run.

## Decisions to write down

Fill these in before you compile. The deployment phases use this sheet as the source of truth.

| Decision | Your answer |
| --- | --- |
| Network (testnet first) | |
| Name | |
| Ticker (3–5 letters) | |
| One-sentence joke | |
| Mascot, described so someone else could draw it | |
| Decimals | 18 |
| Human supply (spoken number) | |
| Raw supply (human × 10^decimals) | |
| Recipient address | |
| Where the contract address will be published | |
| Liquidity: lock details, or "no liquidity" | |

Decimals on EVM tokens are a display convention. Wallets show `raw / 10^decimals`. 18 is the usual choice because it matches ETH. A different number is fine when you write down why, and when every example you publish uses that number.

The recipient should be an address you control. Later transfers are ordinary token transfers, visible on the explorer. That is the audit trail. Avoid a hidden allocation.

## What a keepable name has

A name is ready when a stranger can pass every check below. One failure is enough to pick again.

| Check | Passes when |
| --- | --- |
| Say it | You can say the name on a phone call without spelling it letter by letter |
| Spell it | Five people, told once, spell the name and the ticker |
| Ticker length | 3–5 letters, and it is a readable word or a clean abbreviation |
| Search | A quoted search for the name plus "token" and plus "coin" does not land on a famous coin, product, or company |
| Ticker search | The ticker is not BTC, ETH, SOL, or another asset people already hold |
| Trademark | A search of the trademark office you would actually operate under shows no live mark you would collide with |
| Promise | The name does not say safe, guaranteed, official, or anything about price |
| Person or brand | The name is not a celebrity, a company, or a knockoff of one ("official", "2.0", a one-letter misspelling) |
| Mascot | You can describe the picture in one sentence |
| Handles | A social handle, or an obvious variant, is available on the accounts you will actually post from |
| Still funny at zero | The joke still makes sense if nobody buys it |

## Directions that survive the checklist

These are ways to invent a candidate. They are not tickers to deploy.

1. **A ritual.** Name the thing a specific group already does together (a weekly lunch, a bad habit, a greeting). The token is a label for that ritual.
2. **A five-second drawing.** If you cannot sketch the mascot from memory, the name is doing too much work.
3. **One ordinary word.** Prefer a word a person can pronounce the first time. Run the search before you get attached to it.
4. **A joke that is not the price.** "Number go up" stops being a joke the moment the number goes down. The name has to stand on its own.
5. **A phone-call test.** If you would be embarrassed or unable to say it out loud to a stranger, it is a bad ticker even if it looks clever in a group chat.

## Names that fail, and why

Use these as a grading key. They are illustrations of the checks, not a denylist you memorize.

| Candidate | First check it fails |
| --- | --- |
| GuaranteedMoon | Promise. The name is a claim about price |
| SafeBark | Promise. "Safe" is a claim about risk |
| OfficialPepe | Impersonation of an existing meme |
| ElonRocket2 | Celebrity, and a sequel suffix that exists to borrow fame |
| X | Search and spelling. Nobody can find it, and it collides with a major brand |
| Qzrp | Spelling. Random letters fail the phone-call test |
| BitcoinCashInu | Ticker and name collide with assets people already know, on purpose |

## How to grade one candidate

Pick a word you made up or a ritual name. Run the table. The moment a cell fails, stop and pick another word. Do not "check later" on trademark or on an existing token. A collision means this candidate is finished.

Example of the method, using a placeholder word, **Brindle**:

- Say it: one word, passes the phone test.
- Spell it: ask five people. If they write "Brindal" or "Bryndle", it fails.
- Search `"Brindle" token` and `"Brindle" coin`. If a project already uses it, stop.
- Ticker `BRIN` or `BRNDL`: search those letters the same way. `BRIN` might be short enough and still collide. If it collides, stop.
- Trademark and handles: if either is taken, stop.
- Promise and brand: the word itself makes no price claim and points at no celebrity. That cell can pass while another cell fails.
- Mascot: "a brindle dog" is drawable. That does not rescue a failed search.

Brindle is a worksheet example. It is not a recommendation, and it is not a claim that the name is free.

## Contract shape

`contracts/FixedSupplyToken.sol` is the shape to deploy for this plan:

- The whole supply is minted once, in the constructor, to the recipient you chose.
- There is no owner, no second mint, no pause, and no transfer fee.
- A zero address or a zero supply cannot deploy.

That is a boring contract on purpose. You can read it in one sitting, and an explorer's verified source should match it. Publish the contract address on the site or account you listed in the sheet before you ask anyone else to interact with it. Impersonated token addresses are a common way people lose funds; the correction is a stable place, that you control, where the real address lives.

If you add liquidity on a testnet or later on mainnet, publish the lock: which locker, how much, and when it unlocks. If you are not adding liquidity, say that in the same place. The mainnet gate for this choice is in [DEPLOYMENT.md](DEPLOYMENT.md).

Hidden mint functions, a blacklist that blocks sells, and fake volume are how people get robbed. They are out of scope for this repo. Do not add them to the reference contract.

## After the name survives

Go to [DEPLOYMENT.md](DEPLOYMENT.md) phase 4 and deploy to a testnet with the raw supply from your sheet. Keep the deployer key off mainnet until phase 5 is entirely checked, and keep that key out of git, chat, and shell history. `cast wallet import --interactive` is the path in the deployment doc.
