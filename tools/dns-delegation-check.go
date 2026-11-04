package main

import (
 "fmt"
 "time"
 "github.com/miekg/dns"
)

func main() {
 for _,server:=range []string{"176.99.13.11:53","194.58.117.15:53","1.1.1.1:53","8.8.8.8:53","89.125.120.163:53"} {
  for _,question:=range []struct{name string;typ uint16}{{"ns.chichy.space.",dns.TypeA},{"v.chichy.space.",dns.TypeNS},{"v.chichy.space.",dns.TypeSOA}} {
   q:=new(dns.Msg);q.SetQuestion(question.name,question.typ);q.RecursionDesired=server=="1.1.1.1:53"||server=="8.8.8.8:53"
   response,_,err:=(&dns.Client{Timeout:3*time.Second}).Exchange(q,server)
   fmt.Printf("%s %s %s: ",server,question.name,dns.TypeToString[question.typ])
   if err!=nil {fmt.Println(err);continue}
   fmt.Printf("rcode=%s aa=%v\n",dns.RcodeToString[response.Rcode],response.Authoritative)
   for _,rr:=range append(response.Answer,response.Ns...) {fmt.Println(rr.String())}
  }
 }
}
