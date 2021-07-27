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

#include <ndn-svs/core.hpp>
#include <ndn-svs/store-memory.hpp>
#include <ndn-svs/svspubsub.hpp>

#include <ndn-cxx/util/random.hpp>

#include <thread>
#include <chrono>
#include <vector>
#include <thread>
#include <string>
#include <iostream>

using namespace ndn::svs;
using namespace std::chrono_literals;

class SVSUAV {

public:
    SVSUAV(ndn::Name syncPrefix)
            : m_running(true),
              m_syncPrefix(syncPrefix),
              m_uavPrefix("/uav"){

        instanciateSync();

        // The UaV needs to serve all participants data
        face.setInterestFilter("/",
                               bind(&SVSUAV::onDataInterest, this, _1, _2),
                               nullptr, // RegisterPrefixSuccessCallback is optional
                               bind(&SVSUAV::onRegisterFailed, this, _1, _2));
    }

    void
    run() {
        std::thread thread_svs([this] { face.processEvents(); });

        thread_svs.join();
    }

    void instanciateSync() {
        std::cout << "Create SVS Instance" << std::endl;

        // Use HMAC signing
        SecurityOptions securityOptions;
        securityOptions.interestSigningInfo.setSigningHmacKey("dGhpcyBpcyBhIHNlY3JldCBtZXNzYWdl");

        m_svspubsub = std::make_shared<SVSPubSub>(
                m_syncPrefix,
                m_uavPrefix,
                face,
                std::bind(&SVSUAV::onMissingData, this, _1),
                securityOptions);

        m_svspubsub->subscribeToPrefix(
                ndn::Name("/position"), [&](SVSPubSub::SubscriptionData subData) {
                    // Todo: Log received Data
                    const unsigned long data_size = subData.data.getContent().value_size();
                    const std::basic_string<char> content_str((char *) subData.data.getContent().value(), data_size);

                    std::cout << "Got Data: " << subData.producerPrefix << "[" << subData.seqNo << "] : "
                              << subData.data.getName()
                              << std::endl;

                    std::shared_ptr<ndn::Data> data = std::make_shared<ndn::Data>(subData.data);
                    m_dataStore.insert(*data);
                });
    }

    void publishData(const ndn::Data &data) {
        m_svspubsub->publishData(data);
    }

    void
    onMissingData(const std::vector<ndn::svs::MissingDataInfo> &v) {
    }

    void
    onRegisterFailed(const ndn::Name &prefix, const std::string &reason) {
        std::cerr << "ERROR: Failed to register prefix '" << prefix
                  << "' with the local forwarder (" << reason << ")" << std::endl;
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

protected:
    bool m_running;
    ndn::Face face;
    ndn::Name m_syncPrefix;
    ndn::Name m_uavPrefix;
    ndn::security::SigningInfo m_signingInfo;
    ndn::KeyChain m_keyChain;
    ndn::svs::MemoryDataStore m_dataStore;

    std::shared_ptr<SVSPubSub> m_svspubsub;

};

int main(int argc, char **argv) {
    ndn::Name syncPrefix("/ndn/svs");

    SVSUAV program(syncPrefix);
    program.run();
    return 0;
}
