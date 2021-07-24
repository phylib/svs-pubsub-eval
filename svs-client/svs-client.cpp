/* -*- Mode: C++; c-file-style: "gnu"; indent-tabs-mode:nil -*- */
/*
 * Copyright (c) 2012-2021 University of California, Los Angeles
 *
 * This file is part of ndn-svs, synchronization library for distributed realtime
 * applications for NDN.
 *
 * ndn-svs library is free software: you can redistribute it and/or modify it under the
 * terms of the GNU Lesser General Public License as published by the Free Software
 * Foundation, in version 2.1 of the License.
 *
 * ndn-svs library is distributed in the hope that it will be useful, but WITHOUT ANY
 * WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
 * PARTICULAR PURPOSE. See the GNU Lesser General Public License for more details.
 */

#include <iostream>
#include <string>
#include <thread>
#include <vector>
#include <chrono>
#include <ndn-svs/svspubsub.hpp>
#include <ndn-svs/store-memory.hpp>
#include <ndn-cxx/util/random.hpp>

using namespace ndn::svs;
using namespace std::chrono_literals;

class Options {
public:
    Options() {}

public:
    std::string prefix;
    std::string m_id;
};

class Program {
public:
    Program(const Options &options)
            : m_options(options),
              m_running(true),
              m_dataStore(SVSync::DEFAULT_DATASTORE),
              m_rng(ndn::random::getRandomNumberEngine()),
              m_positionDataIntervalDist(1000 * 0.9, 1000 * 1.1), // Position data published every second
              m_voiceDataIntervalDist(10000, 60000), // Voice data published every 10-60 seconds
              m_voiceDataSizeDist(12, 20) { // Size of voice publications between 12 and 20 bytes

        // Use HMAC signing
        SecurityOptions securityOptions;
        securityOptions.interestSigningInfo.setSigningHmacKey("dGhpcyBpcyBhIHNlY3JldCBtZXNzYWdl");

        m_svspubsub = std::make_shared<SVSPubSub>(
                ndn::Name(m_options.prefix),
                ndn::Name(m_options.m_id),
                face,
                std::bind(&Program::onMissingData, this, _1),
                securityOptions);
        m_signingInfo.setSha256Signing();

        m_svspubsub->subscribeToPrefix(
                ndn::Name("/position"), [&](SVSPubSub::SubscriptionData subData) {
                    // Todo: Log received Data
                    const size_t data_size = subData.data.getContent().value_size();
                    const std::string content_str((char *) subData.data.getContent().value(), data_size);

                    std::cout << "Got Data: " << subData.producerPrefix << "[" << subData.seqNo << "] : "
                              << subData.data.getName()
                              << std::endl;
                });

        // Todo: Only subscribe to voice data of the own platoon
        m_svspubsub->subscribeToPrefix(
                ndn::Name("/voice"), [&](SVSPubSub::SubscriptionData subData) {
                    // Todo: Log received Data
                    const size_t data_size = subData.data.getContent().value_size();
                    int segments = subData.data.getFinalBlock()->toNumber();

                    std::cout << "Got Data: " << subData.producerPrefix << "[" << subData.seqNo << "] : "
                              << subData.data.getName()
                              << " ; totalNoSegments = " << segments << std::endl;
                    fetchOutStandingVoiceSegements(subData.data.getName(), segments);
                });

        // Listen to data interests on /voice and Data
        face.setInterestFilter("/voice/",
                               bind(&Program::onDataInterest, this, _1, _2),
                               nullptr, // RegisterPrefixSuccessCallback is optional
                               bind(&Program::onRegisterFailed, this, _1, _2));
        face.setInterestFilter("/position/",
                               bind(&Program::onDataInterest, this, _1, _2),
                               nullptr, // RegisterPrefixSuccessCallback is optional
                               bind(&Program::onRegisterFailed, this, _1, _2));
    }

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
    onMissingData(const std::vector<MissingDataInfo> &v) {
    }

    void
    onRegisterFailed(const ndn::Name &prefix, const std::string &reason) {
        std::cerr << "ERROR: Failed to register prefix '" << prefix
                  << "' with the local forwarder (" << reason << ")" << std::endl;
    }

    void
    onData(const ndn::Interest &, const ndn::Data &data) const {
        std::cout << "Received Data " << data << std::endl;
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
        // Todo: Segfault whenever accessing the in-memory content store
//        auto data = m_dataStore->find(interest);
//        if (data != nullptr)
//            face.put(*data);
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
    void fetchOutStandingVoiceSegements(ndn::Name name, int finalBlockId) {
        ndn::Name withoutSegmentNo = name.getPrefix(name.size() - 1);

        for (int i = 1; i < finalBlockId; i++) {
            ndn::Name toFetch(withoutSegmentNo);
            toFetch.appendSegment(i);

            ndn::Interest interest(toFetch);
            interest.setCanBePrefix(true);
            face.expressInterest(interest,
                                 bind(&Program::onData, this, _1, _2),
                                 bind(&Program::onNack, this, _1, _2),
                                 bind(&Program::onTimeout, this, _1));
        }
    }

    /**
     * Thread loop that publishes position Data
     */
    void
    positionDataPublishingLoop() {
        while (m_running) {
            int delay = m_positionDataIntervalDist(m_rng);
            std::this_thread::sleep_for(std::chrono::milliseconds(delay));
            publishPositionData();
        }
    }

    /**
     * Publish a single position data record with a size of 16 bytes
     */
    void
    publishPositionData() {

        // Generate a block of random Data
        std::array<uint8_t, 16> buf{};
        ndn::random::generateSecureBytes(buf.data(), buf.size());
        ndn::Block block = ndn::encoding::makeBinaryBlock(
                ndn::tlv::Content, buf.data(), buf.size());

        // Data packet
        ndn::Name name("/position");
        name.append(m_options.m_id);
        name.appendTimestamp();

        ndn::Data data(name);
        data.setContent(block);
        data.setFreshnessPeriod(ndn::time::milliseconds(1000));
        m_keyChain.sign(data, m_signingInfo);

        // Todo: Segfault a soon as datastore is used
//        m_dataStore->insert(data);

        // Publishposition Data using publish channel
        m_svspubsub->publishData(data, m_options.m_id);

        // Todo: Log published Data
        std::cout << "Publish position data: " << data.getName() << " (" << buf.size() << " bytes)" << std::endl;
    }

    /**
     * Thread loop that publishes voice Data
     */
    void
    voiceDataPublishingLoop() {
        while (m_running) {
            int delay = m_voiceDataIntervalDist(m_rng);
            std::this_thread::sleep_for(std::chrono::milliseconds(delay));
            publishVoiceData();
        }
    }

    /**
     * Publish a segmented voice data packet. The number of segment is defined by a random distribution.
     *
     * The first segment is synchronized via sync. All other segments need to be retrieved using Interest-Data
     * exchange
     */
    void
    publishVoiceData() {
        // Number of data segments
        int voiceSize = m_voiceDataSizeDist(m_rng);

        ndn::Name name("/voice");
        name.append(m_options.m_id);
        name.appendTimestamp();
        name.appendVersion(0);

        // Create all data segments
        for (int i = 0; i < voiceSize; i++) {

            // Generate a block of random Data
            std::array<uint8_t, 1000> buf{};
            ndn::random::generateSecureBytes(buf.data(), voiceSize);
            ndn::Block block = ndn::encoding::makeBinaryBlock(
                    ndn::tlv::Content, buf.data(), voiceSize);

            // Data packet
            name.appendSegment(i);

            ndn::Data data(name);
            data.setContent(block);
            data.setFreshnessPeriod(ndn::time::milliseconds(1000));
            data.setFinalBlock(ndn::name::Component::fromNumber(voiceSize - 1));
            m_keyChain.sign(data, m_signingInfo);

            // Todo: Segfault a soon as datastore is used
//            m_dataStore->insert(*data);

            // Publish first segment of voice data using publish channel
            if (i == 0) {
                m_svspubsub->publishData(data, m_options.m_id);
                std::cout << "Publish voice data: " << data.getName() << " (" << buf.size() * voiceSize << " bytes)"
                          << std::endl;
            }

            // Todo: Log published Data
        }


    }

public:
    const Options m_options;
    bool m_running;
    ndn::Face face;
    std::shared_ptr<SVSPubSub> m_svspubsub;
    ndn::KeyChain m_keyChain;
    ndn::security::SigningInfo m_signingInfo;
    std::shared_ptr<DataStore> m_dataStore;

    ndn::random::RandomNumberEngine &m_rng;
    std::uniform_int_distribution<> m_positionDataIntervalDist; // Interval for position data publications
    std::uniform_int_distribution<> m_voiceDataIntervalDist; // Interval for voice data publications
    std::uniform_int_distribution<> m_voiceDataSizeDist; // Defines the size in kbyte of published voice data
};

int main(int argc, char **argv) {
    if (argc != 2) {
        std::cout << "Usage: client <prefix>" << std::endl;
        exit(1);
    }

    Options opt;
    opt.prefix = "/ndn/svs";
    opt.m_id = argv[1];

    Program program(opt);
    program.run();
    return 0;
}
