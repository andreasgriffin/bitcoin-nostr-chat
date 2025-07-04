from typing import List


def get_preferred_relays() -> List[str]:
    return [
        "wss://nostr.btc-library.com",
        "wss://nostrue.com",
        "wss://relay.primal.net",
        "wss://nostr.sathoarder.com",
        "wss://nostr.einundzwanzig.space",
        "wss://nostr.vulpem.com",
        "wss://nostr-1.nbo.angani.co",
        "wss://relay.wavlake.com",
        "wss://strfry.openhoofd.nl",
        "wss://rocky.nostr1.com",
        "wss://nostr.bitcoiner.social",
    ]


def get_default_delays() -> List[str]:
    # sources:
    # https://nostr.info/relays/
    # https://nostrwat.ch/
    # https://legacy.nostr.watch/relays/find
    relays = [
        "wss://nostr.vulpem.com",
        "wss://nostr.0x7e.xyz",
        "wss://relay1.xfire.to:",
        "wss://nostr.fbxl.net",
        "wss://hax.reliefcloud.com",
        "wss://social.proxymana.net",
        "wss://dev-relay.lnfi.network",
        "wss://relay.lnfi.network",
        "wss://nostr.thebiglake.org",
        "wss://relay.nostrtalk.org",
        "wss://nostr.bitcoiner.social",
        "wss://no.str.cr",
        "wss://n.ok0.org",
        "wss://relay.nos.social",
        "wss://nostr-verified.wellorder.net",
        "wss://nostr2.girino.org",
        "wss://relay.nostrich.cc",
        "wss://nostr.bilthon.dev",
        "wss://santo.iguanatech.net",
        "wss://nostr.chaima.info",
        "wss://relay.botev.sv",
        "wss://nostr.coincards.com",
        "wss://relay.credenso.cafe",
        "wss://nostr.kalf.org",
        "wss://orangepiller.org",
        "wss://auth.nostr1.com",
        "wss://antisocial.nostr1.com",
        "wss://relay.lifpay.me",
        "wss://relay.illuminodes.com",
        "wss://relay.s-w.art",
        "wss://ithurtswhenip.ee",
        "wss://fiatjaf.nostr1.com",
        "wss://relay.artx.market",
        "wss://cyberspace.nostr1.com",
        "wss://chadf.nostr1.com",
        "wss://nostr.mdip.yourself.dev",
        "wss://relay.openbalance.app",
        "wss://strfry.openhoofd.nl",
        "wss://nostr-1.nbo.angani.co",
        "wss://rocky.nostr1.com",
        "wss://ghost.dolu.dev",
        "wss://articles.layer3.news",
        "wss://relay5.bitransfer.org",
        "wss://nostr.mom",
        "wss://relay.magiccity.live",
        "wss://relay.nuts.cash",
        "wss://bostr.syobon.net",
        "wss://relay.netstr.io",
        "wss://nostr-relay.amethyst.name",
        "wss://relay.hodl.ar",
        "wss://relay.nostrdvm.com",
        "wss://relay.angor.io",
        "wss://relay.davidebtc.me",
        "wss://free.relayted.de",
        "wss://relay.bitcoinveneto.org",
        "wss://relay.sigit.io",
        "wss://frjosh.nostr1.com",
        "wss://relay2.angor.io",
        "wss://relay.degmods.com",
        "wss://nostr.plantroon.com",
        "wss://relay.nostr.net",
        "wss://relay.evanverma.com",
        "wss://nostr.roundrockbitcoiners.com",
        "wss://relay.electriclifestyle.com",
        "wss://ch.purplerelay.com",
        "wss://ch.purplerelay.com",
        "wss://relay.nostromo.social",
        "wss://inbox.azzamo.net",
        "wss://nostrich.zonemix.tech",
        "wss://nostr.brackrat.com",
        "wss://nostr.agentcampfire.com",
        "wss://relay04.lnfi.network",
        "wss://hivetalk.nostr1.com",
        "wss://relay.cosmicbolt.net",
        "wss://rl.baud.one",
        "wss://relay.copylaradio.com",
        "wss://nostr-rs-relay-ishosta.phamthanh.me",
        "wss://relay.primal.net",
        "wss://relay.primal.net",
        "wss://relay.stream.labs.h3.se",
        "wss://nostr.sagaciousd.com",
        "wss://relay.kamp.site",
        "wss://nostr.searx.is",
        "wss://relay.wellorder.net",
        "wss://relay.wellorder.net",
        "wss://nostr.tac.lol",
        "wss://relay.keychat.io",
        "wss://de.purplerelay.com",
        "wss://de.purplerelay.com",
        "wss://de.purplerelay.com",
        "wss://purplerelay.com",
        "wss://purplerelay.com",
        "wss://purplerelay.com",
        "wss://purplerelay.com",
        "wss://nostr.stakey.net",
        "wss://theforest.nostr1.com",
        "wss://theforest.nostr1.com",
        "wss://theforest.nostr1.com",
        "wss://nostr.namek.link",
        "wss://nostr-relay01.redscrypt.org:48443",
        "wss://nostr.sathoarder.com",
        "wss://backup.keychat.io",
        "wss://relay.tapestry.ninja",
        "wss://slick.mjex.me",
        "wss://nostr.girino.org",
        "wss://nostr.girino.org",
        "wss://strfry.bonsai.com",
        "wss://support.nostr1.com",
        "wss://henhouse.social/relay",
        "wss://bostr.bitcointxoko.com",
        "wss://bostr.bitcointxoko.com",
        "wss://bostr.bitcointxoko.com",
        "wss://bostr.bitcointxoko.com",
        "wss://bostr.bitcointxoko.com",
        "wss://bostr.bitcointxoko.com",
        "wss://bostr.bitcointxoko.com",
        "wss://bostr.bitcointxoko.com",
        "wss://bostr.bitcointxoko.com",
        "wss://bostr.bitcointxoko.com",
        "wss://bostr.bitcointxoko.com",
        "wss://bostr.bitcointxoko.com",
        "wss://bostr.bitcointxoko.com",
        "wss://bostr.bitcointxoko.com",
        "wss://relay.drss.io",
        "wss://nostr.myshosholoza.co.za",
        "wss://relay.mostro.network",
        "wss://ae.purplerelay.com",
        "wss://ae.purplerelay.com",
        "wss://ae.purplerelay.com",
        "wss://ae.purplerelay.com",
        "wss://ae.purplerelay.com",
        "wss://ftp.halifax.rwth-aachen.de/nostr",
        "wss://mls.akdeniz.edu.tr/nostr",
        "wss://nostr.gerbils.online",
        "wss://nr.yay.so",
        "wss://airchat.nostr1.com",
        "wss://relay.nostrdice.com",
        "wss://nostr.yael.at",
        "wss://nostr.camalolo.com",
        "wss://tollbooth.stens.dev",
        "wss://dwebcamp.nos.social",
        "wss://relay.livefreebtc.dev",
        "wss://nostr.oxtr.dev",
        "wss://nostr.snowbla.de",
        "wss://strfry.shock.network",
        "wss://relay.gathr.gives",
        "wss://nostr-02.yakihonne.com",
        "wss://relay.usefusion.ai",
        "wss://nostr-pub.wellorder.net",
        "wss://nostr-pub.wellorder.net",
        "wss://nostr-pub.wellorder.net",
        "wss://relay01.lnfi.network",
        "wss://relay01.lnfi.network",
        "wss://nostr.tavux.tech",
        "wss://relay.digitalezukunft.cyou",
        "wss://relay.agorist.space",
        "wss://nostr-rs-relay.dev.fedibtc.com",
        "wss://relay-testnet.k8s.layer3.news",
        "wss://offchain.pub",
        "wss://nostr.community.ath.cx",
        "wss://nostr.dodge.me.uk",
        "wss://nostr.kloudcover.com",
        "wss://relay.satoshidnc.com",
        "wss://relay.nostrhub.fr",
        "wss://relay.notoshi.win",
        "wss://nostr.hifish.org",
        "wss://nostr.einundzwanzig.space",
        "wss://memrelay.girino.org",
        "wss://nostrue.com",
        "wss://vidono.apps.slidestr.net",
        "wss://primus.nostr1.com",
        "wss://primus.nostr1.com",
        "wss://primus.nostr1.com",
        "wss://primus.nostr1.com",
        "wss://primus.nostr1.com",
        "wss://nostr-dev.wellorder.net",
        "wss://nostr-dev.wellorder.net",
        "wss://nostr-dev.wellorder.net",
        "wss://nostr-dev.wellorder.net",
        "wss://nostr.lojong.info",
        "wss://history.nostr.watch",
        "wss://basedpotato.nostr1.com",
        "wss://nproxy.kristapsk.lv",
        "wss://nproxy.kristapsk.lv",
        "wss://relay.mattybs.lol",
        "wss://relay02.lnfi.network",
        "wss://relay02.lnfi.network",
        "wss://me.purplerelay.com",
        "wss://me.purplerelay.com",
        "wss://me.purplerelay.com",
        "wss://me.purplerelay.com",
        "wss://me.purplerelay.com",
        "wss://me.purplerelay.com",
        "wss://relay.sovereign.app",
        "wss://nostr.btc-library.com",
        "wss://relay.stewlab.win",
        "wss://nostr.satstralia.com",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://soloco.nl",
        "wss://nostr.azzamo.net",
        "wss://eu.purplerelay.com",
        "wss://eu.purplerelay.com",
        "wss://eu.purplerelay.com",
        "wss://eu.purplerelay.com",
        "wss://eu.purplerelay.com",
        "wss://eu.purplerelay.com",
        "wss://eu.purplerelay.com",
        "wss://relay.damus.io",
        "wss://relay.damus.io",
        "wss://relay.damus.io",
        "wss://relay.corpum.com",
        "wss://nostr.jfischer.org",
        "wss://nostr.data.haus",
        "wss://in.purplerelay.com",
        "wss://in.purplerelay.com",
        "wss://in.purplerelay.com",
        "wss://in.purplerelay.com",
        "wss://in.purplerelay.com",
        "wss://in.purplerelay.com",
        "wss://in.purplerelay.com",
        "wss://in.purplerelay.com",
        "wss://relay.zone667.com",
        "wss://dikaios1517.nostr1.com",
        "wss://wbc.nostr1.com",
        "wss://relay.coinos.io",
        "wss://nostr.rblb.it:7777",
        "wss://nos.xmark.cc",
        "wss://relay.8333.space",
        "wss://nostr.nordlysln.net:3241",
        "wss://nostr-01.yakihonne.com",
        "wss://relay.geekiam.services",
        "wss://relay.pokernostr.com",
        "wss://bucket.coracle.social",
        "wss://hotrightnow.nostr1.com",
        "wss://nostr.rtvslawenia.com",
        "wss://nostr.carroarmato0.be",
        "wss://nostr.takasaki.dev",
        "wss://nostr.gleeze.com",
        "wss://relay.varke.eu",
        "wss://pareto.nostr1.com",
        "wss://ir.purplerelay.com",
        "wss://ir.purplerelay.com",
        "wss://ir.purplerelay.com",
        "wss://ir.purplerelay.com",
        "wss://ir.purplerelay.com",
        "wss://ir.purplerelay.com",
        "wss://ir.purplerelay.com",
        "wss://ir.purplerelay.com",
        "wss://ir.purplerelay.com",
        "wss://nostr.kungfu-g.rip",
        "wss://nostr-relay.psfoundation.info",
        "wss://relay03.lnfi.network",
        "wss://relay03.lnfi.network",
        "wss://relay03.lnfi.network",
        "wss://relay.nostriot.com",
        "wss://nostream.coinmachin.es",
        "wss://uk.purplerelay.com",
        "wss://uk.purplerelay.com",
        "wss://uk.purplerelay.com",
        "wss://uk.purplerelay.com",
        "wss://uk.purplerelay.com",
        "wss://uk.purplerelay.com",
        "wss://uk.purplerelay.com",
        "wss://uk.purplerelay.com",
        "wss://uk.purplerelay.com",
        "wss://uk.purplerelay.com",
        "wss://relay.wavlake.com",
        "wss://nostr.liberty.fans",
        "wss://relay-rpi.edufeed.org",
        "wss://nostr-03.dorafactory.org",
        "wss://nostr-03.dorafactory.org",
        "wss://lnbits.satoshibox.io/nostrclient/api/v1/relay",
        "wss://lnbits.satoshibox.io/nostrclient/api/v1/relay",
        "wss://lnbits.satoshibox.io/nostrclient/api/v1/relay",
        "wss://lnbits.satoshibox.io/nostrclient/api/v1/relay",
        "wss://lnbits.satoshibox.io/nostrclient/api/v1/relay",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://relay.satlantis.io",
        "wss://nostr.frostr.xyz",
        "wss://relay.tagayasu.xyz",
        "wss://relay1.nostrchat.io",
        "wss://nostr.skitso.business",
        "wss://e.nos.lol",
        "wss://relay.mess.ch",
        "wss://thebarn.nostr1.com",
        "wss://lnbits.papersats.io/nostrclient/api/v1/relay",
        "wss://lnbits.papersats.io/nostrclient/api/v1/relay",
        "wss://lnbits.papersats.io/nostrclient/api/v1/relay",
        "wss://lnbits.papersats.io/nostrclient/api/v1/relay",
        "wss://lnbits.papersats.io/nostrclient/api/v1/relay",
        "wss://lnbits.papersats.io/nostrclient/api/v1/relay",
        "wss://lnbits.papersats.io/nostrclient/api/v1/relay",
        "wss://communities.nos.social",
        "wss://tigs.nostr1.com",
        "wss://nostr.hekster.org",
        "wss://relay.minibolt.info",
        "wss://relay.fr13nd5.com",
    ]

    return list(set(relays))
