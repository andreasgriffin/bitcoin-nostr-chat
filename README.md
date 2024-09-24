# A Nostr Chat with participant discovery

All users know a shared secret (like a bitcoin wallet descriptor). This allows them to find each other. 
  * Even if this shared secret leaks, the attacker can only spam the discovery option, the actual chats stay secure

The actual single and group chats are based on a newly generated secret keys for each participant.
  * Each participant has to be manually accepted to be added to the group chat
  * Chats with participants use NIP17 and group messages are simply NIP17 messages to each participant 

Export and restoring of the nsec and with it restoration of all messages of the relays


