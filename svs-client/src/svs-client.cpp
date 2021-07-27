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
#include <ndn-svs/svspubsub.hpp>
#include <ndn-cxx/util/random.hpp>
#include "AbstractProgram.h"

using namespace ndn::svs;
using namespace std::chrono_literals;

class SVSProgram : public AbstractProgram {

public:
    SVSProgram(ndn::Name syncPrefix, ndn::Name participantPrefix)
            : AbstractProgram(syncPrefix, participantPrefix) {

        instanciateSync();
    }

    void instanciateSync() override {
        std::cout << "Create SVS Instance" << std::endl;

        // Use HMAC signing
        SecurityOptions securityOptions;
        securityOptions.interestSigner->signingInfo.setSigningHmacKey("dGhpcyBpcyBhIHNlY3JldCBtZXNzYWdl");

        m_svspubsub = std::make_shared<SVSPubSub>(
                m_syncPrefix,
                m_participantPrefix,
                face,
                std::bind(&SVSProgram::onMissingData, this, _1),
                securityOptions);

        m_svspubsub->subscribeToPrefix(
                ndn::Name("/position"), [&](SVSPubSub::SubscriptionData subData) {
                    // Todo: Log received Data
                    const unsigned long data_size = subData.data.getContent().value_size();
                    const std::basic_string<char> content_str((char *) subData.data.getContent().value(), data_size);

                    std::cout << "Got Data: " << subData.producerPrefix << "[" << subData.seqNo << "] : "
                              << subData.data.getName()
                              << std::endl;
                });

        m_svspubsub->subscribeToPrefix(
                ndn::Name("/voice").append(m_platoonPrefix), [&](SVSPubSub::SubscriptionData subData) {
                    // Todo: Log received Data
                    const unsigned long data_size = subData.data.getContent().value_size();
                    int segments = subData.data.getFinalBlock()->toNumber();

                    std::cout << "Got Data: " << subData.producerPrefix << "[" << subData.seqNo << "] : "
                              << subData.data.getName()
                              << " ; finalBlockId = " << segments << std::endl;
                    fetchOutStandingVoiceSegements(subData.data.getName(), segments);
                });
    }

    void publishData(const ndn::Data &data) override {
        m_svspubsub->publishData(data);
    }

    void
    onMissingData(const std::vector<ndn::svs::MissingDataInfo> &v) {
    }

protected:
    std::shared_ptr<SVSPubSub> m_svspubsub;

};

int main(int argc, char **argv) {
    if (argc != 2) {
        std::cout << "Usage: client <prefix>" << std::endl;
        exit(1);
    }

    ndn::Name syncPrefix("/ndn/svs");
    ndn::Name participantPrefix(argv[1]);

    SVSProgram program(syncPrefix, participantPrefix);
    program.run();
    return 0;
}
