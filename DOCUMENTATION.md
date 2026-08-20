# Telegram AI Hub — Installation and User Guide

Support: **contact@kone-adama.com**  
WhatsApp: **+212 781 488 538**

## 1. Requirements

- Odoo Community or Enterprise on Odoo.sh or an on-premise server.
- A public HTTPS URL reachable by Telegram.
- A Telegram account with access to the official BotFather.
- An OpenAI API key supplied and controlled by the customer.

Odoo Online does not allow custom server modules and is therefore not supported.

## 2. Install the application

1. Copy the `telegram_ai_hub` directory into an Odoo addons path.
2. Restart the Odoo service.
3. Enable developer mode and update the Apps list.
4. Search for **Telegram AI Hub** and click **Install**.

## 3. Create the Telegram bot

1. Open Telegram and start a conversation with **@BotFather**.
2. Send `/newbot`.
3. Choose a display name and a username ending in `bot`.
4. Copy the generated bot token and keep it confidential.

## 4. Use the guided setup assistant

1. Open **Telegram AI Hub → Configuration → Setup Assistant**.
2. Paste the Telegram bot token and test the connection.
3. Select the active bot connection.
4. Install the webhook and confirm the success notification.
5. Configure the AI provider.
6. Authorize the first Telegram user.

## 5. Configure the AI provider

1. Open **Telegram AI Hub → Configuration → AI Providers**.
2. Create or open a provider.
3. Enter the API key, endpoint and response model.
4. Select a transcription model if voice messages are required.
5. Configure the timeout, tool rounds and system instructions if needed.
6. Test the connection and activate the provider.

The API key is configured in Odoo and is not hard-coded in the application.

## 6. Authorize employees

1. Ask the employee to send a message to the bot.
2. Open **Authorized Telegram Users** in Odoo.
3. Use the permanent numeric Telegram ID, not only the username or display name.
4. Link the identity to the corresponding active internal Odoo user.
5. Enable only the contact, CRM, sales and accounting capabilities required by the employee.

The linked Odoo user's access rights and record rules remain active.

## 7. Example requests

- “List the unpaid customer invoices.”
- “Show the detailed lines of invoice INV/2026/0001.”
- “Give me the products and quantities of sales order S00042.”
- “Create a contact named Maria Lopez with email maria@example.com.”
- “Create a CRM opportunity for Atlas Company.”
- “How many units of Product A are currently available?”
- “What appointments do I have this week?”

## 8. Voice messages

Send a Telegram voice note as you would send a text request. The configured
transcription model converts the audio to text, and the assistant processes the
resulting request with the same access controls.

## 9. Human handover

When a request needs manual intervention, transfer the conversation to an Odoo
operator. The operator can review its history, reply, close the conversation or
resume automated handling.

## 10. Troubleshooting

### The bot does not answer

- Test the Telegram token from the bot connection.
- Confirm that the Odoo base URL uses a valid public HTTPS certificate.
- Reinstall and verify the webhook.
- Check that the connection and AI provider are active.
- Review the conversation and message error fields in Odoo.

### A user is denied access

- Verify the permanent Telegram numeric ID.
- Confirm that the linked Odoo user is active and internal.
- Review the user's Odoo groups and record rules.
- Review the Telegram capability flags.

### Invoice or sales-order lines are missing

- Confirm that the linked Odoo user can read the parent document and its lines.
- Use the exact document reference in the request.
- Review the message error and AI tool audit information.

## 11. Installation assistance

ResilientByte Maroc accompanies customers during the first installation and
configuration. After purchase, contact us with your Odoo version, deployment type
and preferred availability. Never send production passwords, bot tokens or API keys
in a public message.
