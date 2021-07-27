//
// Created by phmoll on 7/26/21.
//

#ifndef SVSPUBSUBEVALUATION_ABSTRACTPROGRAM_H
#define SVSPUBSUBEVALUATION_ABSTRACTPROGRAM_H

#include <thread>
#include <ndn-cxx/util/random.hpp>
#include <ndn-svs/store-memory.hpp>
#include <chrono>
#include <vector>
#include <thread>
#include <string>
#include <iostream>

using namespace std::chrono_literals;

class AbstractProgram {

public:
    AbstractProgram(ndn::Name syncPrefix, ndn::Name participantPrefix)
            : m_running(true),
              m_syncPrefix(syncPrefix),
              m_participantPrefix(participantPrefix),
              m_rng(ndn::random::getRandomNumberEngine()),
              m_positionDataIntervalDist(1000 * 0.9, 1000 * 1.1), // Position data published every second
              m_voiceDataIntervalDist(10000, 60000), // Voice data published every 10-60 seconds
              m_voiceDataSizeDist(12, 20) { // Size of voice publications between 12 and 20 bytes

        m_signingInfo.setSha256Signing();
    }

    virtual void instanciateSync() = 0;

    virtual void publishData(const ndn::Data &data) = 0;

    void
    run() {
        std::thread thread_svs([this] { face.processEvents(); });
        std::thread thread_position([this] { this->positionDataPublishingLoop(); });
        std::thread thread_voice([this] { this->voiceDataPublishingLoop(); });

        thread_svs.join();
        thread_position.join();
        thread_voice.join();
    }

protected:

    void
    onRegisterFailed(const ndn::Name &prefix, const std::string &reason) {
        std::cerr << "ERROR: Failed to register prefix '" << prefix
                  << "' with the local forwarder (" << reason << ")" << std::endl;
    }

    void
    onData(const ndn::Interest &, const ndn::Data &data) const {
        std::cout << "Got Data: " << data.getName() << std::endl;
        // Todo: Log received Data packet
    }

    void
    onNack(const ndn::Interest &, const ndn::lp::Nack &nack) const {
        // should not happen since we do not send Nacks
        std::cout << "Received Nack with reason " << nack.getReason() << std::endl;
    }

    void
    onTimeout(const ndn::Interest &interest) const {
        // Todo: Log that data one was not able to retrieve Data

        std::cout << "Timeout for " << interest << std::endl;
    }

    /**
     * Data interests should be replied from our in-memory content store
     * @param interest
     */
    void
    onDataInterest(const ndn::InterestFilter &, const ndn::Interest &interest) {
        auto data = m_dataStore.find(interest);
        if (data != nullptr) {
            face.put(*data);
        }
    }

    /**
     * Voice data is segmented. The first segment of voice data has the final block id set. This Data is sent over
     * the PubSub channel. All subsequent data's have to be fetched over interest-data exchange.
     *
     * This method emits interests to get all segments starting from the second (seg=1) to the final block id.
     *
     * @param name Name of the first data item (including seqment number)
     * @param finalBlockId Final Block ID
     */
    void fetchOutStandingVoiceSegements(ndn::Name name, int finalBlockId);

    /**
     * Thread loop that publishes position Data
     */
    void positionDataPublishingLoop();

    /**
     * Publish a single position data record with a size of 16 bytes
     */
    void publishPositionData();

    /**
     * Thread loop that publishes voice Data
     */
    void
    voiceDataPublishingLoop();

    /**
     * Publish a segmented voice data packet. The number of segment is defined by a random distribution.
     *
     * The first segment is synchronized via sync. All other segments need to be retrieved using Interest-Data
     * exchange
     */
    void publishVoiceData();

protected:
    bool m_running;
    ndn::Face face;
    ndn::Name m_syncPrefix;
    ndn::Name m_participantPrefix;
    ndn::security::SigningInfo m_signingInfo;
    ndn::KeyChain m_keyChain;
    ndn::svs::MemoryDataStore m_dataStore;

    ndn::random::RandomNumberEngine &m_rng;
    // Interval for position data publications
    std::uniform_int_distribution<> m_positionDataIntervalDist;
    // Interval for voice data publications
    std::uniform_int_distribution<> m_voiceDataIntervalDist;
    // Defines the size in kbyte of published voice data
    std::uniform_int_distribution<> m_voiceDataSizeDist;
};


#endif //SVSPUBSUBEVALUATION_ABSTRACTPROGRAM_H
