<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:fo="http://www.w3.org/1999/XSL/Format"
  xmlns:mods="http://www.loc.gov/mods/v3"
  version="1.0">

  <xsl:param name="IMG_DIR"/>

  <xsl:output method="xml"/>


  <xsl:template match="/">
    <fo:root xmlns:fo="http://www.w3.org/1999/XSL/Format">
      
      <fo:layout-master-set>
        
        <fo:simple-page-master master-name="basic"
          page-height="11in" 
          page-width="8.5in"
          margin-top="0.2in" 
          margin-bottom="0.5in"
          margin-left="0.5in" 
          margin-right="0.5in">
          <fo:region-body margin-bottom="0.7in" 
            column-gap="0.25in" 
            margin-left="0.5in" 
            margin-right="0.5in" 
            margin-top="0.5in"/>
          <!-- named header region; to keep from displaying on first page -->
          <fo:region-before extent="1.0in" region-name="header"/>
          <fo:region-after extent="0.5in" region-name="footer"/>
        </fo:simple-page-master>
        
        <!-- basic pages only-->
        <fo:page-sequence-master master-name="all-pages">
          <fo:repeatable-page-master-reference master-reference="basic"/>
        </fo:page-sequence-master>
        
      </fo:layout-master-set> 	
      
      <fo:page-sequence master-reference="all-pages">

        <!-- header ? -->
<!--        <fo:static-content flow-name="header">
           <fo:block font-family="any" left="0in" font-size="10pt" margin-left="0.25in">
            <xsl:apply-templates select="//div[@id='header']" mode="header-footer"/>
           </fo:block>
      </fo:static-content> -->

<!-- footer ? -->
<!--      <fo:static-content flow-name="firstpage-footer">
        <fo:block text-align="start" font-family="any" font-style="italic"
          font-size="10pt" margin-left="0.5in" margin-right="0.5in">
            <xsl:apply-templates select="//div[@id='firstpage-footer']" mode="header-footer"/>
        </fo:block>
      </fo:static-content> -->

      <fo:flow flow-name="xsl-region-body">
        <fo:block text-align="center" font-weight="bold" 
                  font-size="18pt" margin-bottom="1in">
        <fo:external-graphic>
          <xsl:attribute name="src"><xsl:value-of 
          	select="concat('file://', $IMG_DIR, '/logo_hz_280bk.png')"/></xsl:attribute>
        </fo:external-graphic>
        </fo:block>

        <fo:block text-align="center" font-weight="bold" margin-bottom="0.5in">
          <xsl:apply-templates select="mods:mods/mods:titleInfo"/>
        </fo:block>

        <xsl:apply-templates select="mods:mods/mods:identifier[@type='uri']"/>
         
         <!-- <xsl:apply-templates/> -->

      </fo:flow>
      
      </fo:page-sequence>	
      
    </fo:root>

  </xsl:template>

  <xsl:template match="mods:mods/mods:titleInfo">
    <fo:block font-size="14pt">
    <xsl:apply-templates select="mods:title"/>
    <xsl:apply-templates select="mods:subTitle"/>
    </fo:block>
    <fo:block font-size="12pt">
    <xsl:apply-templates select="mods:partName"/>
    <xsl:if test="mods:partName and mods:partNumber">
      <xsl:text>: </xsl:text>
    </xsl:if>
    <xsl:apply-templates select="mods:partNumber"/>
    </fo:block>
  </xsl:template>

  <xsl:template match="mods:titleInfo/mods:subTitle">
    <xsl:text>: </xsl:text><xsl:apply-templates/>
  </xsl:template>

  <xsl:template match="mods:identifier[@type='uri']">
    <fo:block>
      <xsl:text>Permanent URL: </xsl:text>
      <!-- TODO: make clickable link -->
      <xsl:apply-templates/>
    </fo:block>
  </xsl:template>

  
</xsl:stylesheet>